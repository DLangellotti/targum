# targum — design

**This file governs every visible surface.** It is not advisory and it is not a starting
point to riff on. Read it before changing anything visual.

It replaced `Design updated.pdf` on 2026-08-29 as the authority. The PDF is where all of
this came from and is still worth looking at for the drawings — the mark at four sizes, the
lockups, the type specimens — but where the two disagree, **this file wins**, and a change
made here is the change. The PDF cannot be edited by the people and processes that edit the
code, which is how it came to be out of date in three places while still being called
binding.

Section numbers are the PDF's, kept because the stylesheets cite them: `reader.css` says
"Functional colour (§4)" and "Gloss (§9) is light on glass" and those references should keep
resolving. §12 is new and records where the code knowingly departs.

`tests/test_brand.py` enforces the half a machine can check — palette, radii, type scale,
focus colour, no emoji, lowercase name, no exclamation marks, no gamification, motion always
optional. **When a brand test fails, the code is wrong, not the test.** Change the test only
when this file changes first.

---

## 1 · The idea

targum is a reading app for language learners: a text and its translation held in parallel,
sentence by sentence. The identity extends the reading surface rather than sitting on top of
it — **the brand is the page**.

The identity is matte; the UI may shine, measured. **The mark, lockup and wordmark are flat
forever** — no gradients, bevels or metallic ramps on them, ever. Interactive and celebratory
UI elements may carry the gloss recipe and hover lift in §9. Metallic gold ramps stay banned
everywhere.

**A text that carries media opens as its media.** The player stands and is named; a
picture is on. Nothing plays until pressed, and the text is still the page. This replaced
"the reader is a reader, not a player" on 2026-09-03 — see §12. What that sentence also
meant still holds: engagement is welcome, arcade is not. Streaks,
goals and milestones are a ledger: real counts in serif tabular numbers, leaf for
achievement, iris for novelty, celebration in type rather than motion. No mascots, no flags
(one exception, the language menu — §12, 2026-09-14), no emoji.

Positions deliberately avoided: heritage gold (the Orthodox-publisher shelf), Koren's
burgundy `#800020`, the language-app orange, and everyone's blue.

## 2 · The mark

Two staggered columns: the source begins, the translation follows one line later. **The ink
column is always the source; the accent column is always the translation.** Script-neutral by
construction — it carries Hebrew, Arabic, Cyrillic and Latin equally.

- Clear space: half the mark's height on all sides.
- Minimum size: 16 px on screen, 4 mm in print.
- Single-colour versions — all-ink on paper, all-paper on ink, all-accent — are all legal.
  The accent is optional in the mark; it is never the mark.
- Two-colour on brand surfaces; single-colour everywhere small or third-party.

## 3 · The lockup

- The wordmark is the reading face at weight 600, **always lowercase** — even at sentence
  start — with −0.01em tracking.
- Lockup minimum width 72 px / 18 mm; below 24 px the wordmark drops and the monogram
  stands alone.
- RTL: the mark mirrors legitimately. The stagger flips with the page — that is the mark
  reading right-to-left, not a mistake — and leads from the right. The Hebrew wordmark is
  תרגום, same face and weight.
- **The mark always leads the reading direction.**

## 4 · Colour

Warm paper, warm ink, one accent hue. There is one look, and it is light (§12, 2026-09-19).
The second column below is the **ink surface** — §9's inverted block, a film's letterbox, the
public pages' band: a dark surface *on* a light page, never a dark page. The accent
**splits** across the two: a deep cut works on paper, a pale cut works on ink. The pale cut appears on light
surfaces only as a 12–22% wash (kept words, highlights, row tints). What keeps this off the
ArtScroll shelf is not the hue but the finish: **always flat, never a ramp, never a large
field, never text below the ratios shown.**

| role | on paper | on ink | use |
|---|---|---|---|
| page | `#fbf9f5` | `#171614` | surface |
| page · raised | `#f3efe7` | `#201e1b` | cards, hovers |
| rule | `#e2dcd1` | `#322e29` | hairlines only |
| ink | `#1c1a17` · 15.7:1 | `#e6e1d8` · 13.9:1 | reading text — AAA |
| muted | `#6b645c` · 5.5:1 | `#9a9288` · 5.9:1 | translation, chrome — AA |
| accent · working | `#7a5c38` · 5.8:1 | `#c8a778` · 8.0:1 | links, buttons, interactive |
| accent · wash | `#c8a778` at 12–22% | `#c8a778` at 12–22% | kept words, highlights; never text |

**One accent hue, and it is rationed.** Reserved for the single primary action in a view and
for what the reader has kept. Selection is quiet ink (`#6b645c` with paper text), never
accent. The accent is never body text and never a large field.

### Functional colour

The page stays calm; the moments get colour. Three brighter hues are allowed in UI features
— feedback, progress, badges, charts — **never in the identity**. One functional hue per
moment; flat always; text only at these working cuts; washes at 12–22%.

- **leaf** `#5a7340` (5.0:1) · on ink `#a8c37e` (9.3:1) — progress, success, "known"
- **clay** `#b4553f` (4.6:1) · on ink `#e0937d` (7.4:1) — cost, errors, destructive
- **iris** `#6b5a8e` (5.7:1) · on ink `#b3a3d6` (7.9:1) — phrases, discovery, "new"

Green and purple are the two positions nobody in the category owns; blue and orange stay
out. The mark, lockup and wordmark remain ink + gold only.

Worth knowing while reading the code: clay sits close to the accent under protanopia, so an
error must never rest on colour alone — the wording carries it too, which §6 already
requires.

### Bright set — peak moments

Four vivid colours for highs and rare circumstances. They live on ink panels as fills, chips
and glyphs; on paper only as ≥3:1 graphics; text at these colours only on ink. Still one hue
per moment.

- **sun** `#e2a33c` (8.2:1 on ink) — streak milestones, the daily spark
- **leaf-bright** `#7ba646` — goal smashed, personal best
- **iris-bright** `#8e74c9` (4.7:1) — rare finds, a perfect week
- **rose** `#c2517a` (4.1:1, large glyphs only) — records, special events

Measured, `--sun` (2.09:1) and `--leaf-bright` (2.70:1) do not reach 3:1 on paper, so those
two are **ink-panel only**.

### Supporting

Focus ring `#b8935e`. The mark's translation column on paper is its own value, `#a5824f` —
the working accent goes muddy at 22 px wide. Deep paper is structural: desk `#ece7de`, rail
`#e7e1d6`, divider `#e6e1d8` — never a text background.

**The knowledge ramp climbs to leaf, not gold** — see §12.

## 5 · Type

Type is where targum's presence comes from. The wordmark face is the reading face — the brand
is the page.

- **Reading (Latin):** Iowan Old Style → Palatino Linotype → Palatino → Georgia → Times New
  Roman → serif.
- **Reading (Hebrew):** its own stack, not appended to the Latin one, and **carried in the
  page rather than named** — see §12.
- **UI:** `system-ui`. **Details:** `ui-monospace` for keys, hexes and counts (tabular
  numerals).
- **Scale:** display 1.75rem/600 · headings 1.5em/600 · reading 1.0625rem (17px) · gloss
  0.9375rem · UI 0.8125rem · labels 0.6875rem uppercase at 0.06em.
- **Landing display:** 2.75rem/600, 2.25rem under 40rem — the one headline of a public
  landing page, and nowhere inside the product. Line-height 1.1, `text-wrap: balance`.
  Added 2026-08-31; see §12.
- **Measure:** one reading column is 34rem; the source–translation gutter is 2.5rem.

**Bilingual parity:** Hebrew and Latin share every screen at the same font-size — **never
scale Hebrew down**. Parity comes from leading: **1.75 Latin, 1.95 Hebrew**.

## 6 · Voice

Two registers, and which one applies depends on who is reading.

- **Inside the product, targum talks to the reader, warmly and directly.** It speaks as
  "we" and to "you", the way a person behind a counter would: "Thanks for the link. We're
  working out how long it'll take." Thank the reader when they hand us something — a link,
  a file, a correction. Say what we are doing while we do it ("We're reading the page"),
  and what happens next in the reader's own time ("Your first chapter will be ready in
  about 4 minutes"). Contractions are welcome. Somebody who has already chosen targum is
  not sold to again, and is never talked down to. See §12, 2026-09-13.
- **Inside the product there is no price.** The reader pays by the month; what a thing
  takes is said in minutes and in their hours, never as a price, a quote or a sale.
- **On public pages — landing, pricing, the weekly's front — the copy sells.** A stranger
  owes targum nothing and will leave in seconds, so lead with what they get, name it in
  their words rather than ours, and ask for the sign-up plainly. Feature names that only
  make sense inside the team ("the shelf", "scenes", "the weekly") are the failure mode
  here, not enthusiasm.
- **Persuasion yes, inflation no.** No superlatives, no manufactured urgency, no claim the
  product cannot keep. The strongest line is usually the specific one: "an English
  translation beside every line" beats "the best way to read Hebrew."
- Second person for the reader's actions ("Tap a word…").
- **A control names what the person will do with this thing: read, listen or watch.**
  "The reader" is the product's word for the page and for whoever is at it, and it stays
  (§1, §13). But many come to listen and to watch (David, 2026-09-19), and a button that
  says "Start reading" over a video is talking to somebody else. A row knows what it
  carries, so its verb follows it — Continue watching, Start listening — and where no
  row is known yet the word is the neutral one: Open. The ledger counts "days on targum"
  and "words learned on targum", not days reading. targum-internal#337.
- An error says in words what went wrong; colour alone never carries it — see §4.
- **The name is always lowercase: targum**, even at sentence start.
- No emoji, no exclamation marks, **no invented currency** — engagement counts real things
  ("12 days reading", "500 words known"), never XP, points or levels. Milestones brag the
  brand's way: "the page is 31% quieter than when you began." Missed streak days are quiet,
  never red.
- **And short.** Warm is not long. A line is one or two sentences, and a button or a link
  is one or two words: "Send a link", not "Email me a link"; "Delete", not "Move to the
  trash". No filler that says nothing — no "Oops", no "Awesome", no "Just a moment
  please" — and no answering the question nobody asked.
- **When something goes wrong, we own it** and say what the reader can do: "We couldn't
  open that page. Try pasting the text itself." Never blame the reader, never go vague.
- **What the chat writes is chrome when it is English and content when it is Hebrew.**
  Every English sentence the assistant produces obeys this section in full; the Hebrew
  it writes for a learner is a text, and the English rules do not reach it. A model's
  output is in no stylesheet or template, so `test_brand.py` cannot see it: the rules
  live in `chat/prompts.py`, and `test_chat_prompts.py` asserts over that file that each
  is still said. Added 2026-09-05; see §12.

## 7 · Iconography

No icon font, no emoji, no icon library. Icons are tiny inline SVG strokes at text weight:
**16px viewBox, no fill, stroke `currentColor` at 1.4, round caps** — line diagrams of what
they do (the three reading-mode glyphs are literally the three layouts). Typed characters
elsewhere: ← → per reading direction, × to close and after a number as a multiplier
(1.25×), A− A+ as themselves. (`?` was one of them until 2026-09-19: the reader's
keys say "Keys" now — §12, "The picture's keys say what they do".) The box's three actions are glyphs — a microphone, an
arrow, a loudspeaker, from `_glyphs.html.j2` — with the word kept as the control's label
(2026-09-10); the `+` beside them stays typed.

## 8 · Surfaces, states, motion

- In the reader, resting surfaces are flat: raised paper, 1px rule border, radii 4–8px —
  exactly 4 controls, 5 rows, 6 cards, 8 panels, 999 pills, never snapped. Shadows exist
  only on floating overlays (gloss card, menus, tips). **On the desk (§13, since
  2026-09-11) the scale is its own** — 8 controls, 12 rows and fields, 16 cards, 24
  sheets and floating panels, 999 pills — and depth is three tiers rather than a line:
  rest, raised, floating. A hairline (ink at 8%) stands only where two same-tone
  surfaces meet.
- Hover lifts muted to ink; row hovers are 7–10% accent washes. Selection is ink-soft with
  paper text. Focus is a 2px `#b8935e` ring.
- **Motion is rare and purposeful:** the mode pill slides 240ms on
  `cubic-bezier(0.32, 0.72, 0, 1)`; mode switches settle with a 200ms fade. On the desk
  one curve moves everything, `cubic-bezier(0.2, 0.8, 0.2, 1)`, 240ms in and 160ms out,
  and a press gives to 0.98. Everything honours `prefers-reduced-motion`.
- **RTL is structural, not cosmetic:** logical CSS properties throughout, so every layout
  mirrors itself. Never `left`/`right`.
- **A control a thumb presses answers a tap over 44px.** Where a coarse pointer is the
  input — `(hover: none) and (pointer: coarse)` — every control in the chrome reaches at
  least 44px, drawn at that size or given the reach with a centred `::after`. The icon
  itself may stay small; what must be 44px is what answers the tap.

  **The reach may cross a margin; it may not cross the text.** The per-line play button
  takes its 44px and is safe doing so because it stands in the gutter, outside the pair —
  a reach that grew over the words instead would take taps meant for them, and tapping a
  word is what the reader came to do.

  The rule lived in `reader.css` as two selector lists nobody had written down, and it
  drifted: the picture's × had its 44px while the mode and corner keys beside it did not,
  and neither did the speed or the picture toggle in the strip. `test_brand.py` pins it
  now, and the list in that test is the registry — a new control belongs in it the day it
  is drawn.

## 9 · Building screens

The palette is warm, but screens must not be a wash of brown on beige. **Contrast is the
engagement mechanism:** near-white pages, full-ink text, hue concentrated where the reader
acts.

- **Text is ink.** Anything the reader came for — body text, headings, numbers they earned —
  is full ink (15.7:1 on paper, 13.9:1 on an ink block). Muted `#6b645c` is for genuinely secondary lines
  only (translations at rest, captions, metadata), never for primary content, and never
  below 13px on raised paper. Brown `#7a5c38` is a link-and-button colour, never a text
  colour for paragraphs.
- **The page is near-white, not beige.** Text sits on `#fbf9f5` / `#faf8f4` only. The deep
  paper tones are structural — desks, rails, dividers — never a text background.
- **One raised layer per view.** Raised paper `#f3efe7` marks one level of grouping; stacking
  beige on beige is exactly what makes a screen sleepy. If a card needs a card, use a
  hairline.
- **Ink inversion is the wake-up move.** One block per screen may invert to the dark surface
  (`#171614` with `#e6e1d8` text and pale-cut hues) — stats, a milestone, a hero moment. It
  is the highest contrast available; spent on one block it is striking, spent on three it is
  a dark theme — and there is no dark theme (§12, 2026-09-19).
- **Hue budget:** roughly 80% paper + ink, 15% structural neutrals, 5% hue — and the 5% goes
  where the reader acts or achieved something, never into decoration.
- **Interactive means visibly different.** Every tappable element carries ink or a hue:
  ink-filled calls to action, accent links and working buttons, ink-bordered secondary
  buttons, leaf progress, iris novelty. **A beige button on a beige card is forbidden.**
- **Calls to action are ink.** The button that asks somebody to act — sign in, start
  reading, the door on a public page — is the max-contrast pair: ink-filled, paper text,
  weight 600; on an inverted block it flips to paper with ink text. The accent keeps the
  product's working actions (play, Save, Send it) and links, where its calm is the
  point — as a call to action on warm paper it whispered. Added 2026-08-31; see §12.
- **The chat page is one more surface, not a widget.** `/chat` takes the rules of any
  page inside the product: the thread is its one raised layer; the reader's lines and
  targum's are the same ink under a quiet label, never two colours of bubble; sending is
  a working action and takes the accent; the send button, the new-conversation door and
  the rows of the list are in `test_brand.py`'s thumb registry. Added 2026-09-05.
- **The box is the front door, and it is not a raised layer.** The same field stands
  on Learn, under the ledger's own sentence, and on the conversation page, from one file
  (`_composer.html.j2`): a hairline field on paper, Send in the accent, Speak and the
  `+` for a file as ink-bordered working controls. On both pages something else has the
  view's one raised layer. Added 2026-09-06; see §12.
- **Numbers at display sizes are ink or leaf.** Gold is the record colour inside charts, not
  a headline colour; gold display type on cream is the sleepy publisher look this brand
  exists to avoid.
- **Max-contrast pair.** Feature and engagement screens may step up from paper/ink to
  `#fffdf9` on `#121110` (18.6:1 measured) when the moment should feel switched on.
- **Gloss recipe.** Interactive and celebratory elements may carry a top-down white sheen:
  ≤14% (`--gloss`) on primary buttons and progress fills, ≤22% (`--gloss-strong`) on
  celebration chips, plus a soft hover lift (`--lift`: 0 2px 10px at 10%). Gloss is **light
  on glass, never metal**: one sheen per element, never on the mark or lockup, never a
  gold-to-gold ramp, never on a resting text surface.

## 10 · Never

- Metallic golds, bevels, emblems, or any gradient on the mark, lockup or wordmark —
  "printed sefer" is the wrong century and the wrong product. (UI gloss per §9 is the only
  permitted sheen.)
- Mascots, squircle app-mark clichés, flag imagery — texts, not countries. (The language
  menu's small flags are the one exception: §12, 2026-09-14.)
- Burgundy `#800020` (Koren's), orange (the language-app default), blue (everyone's).
- Ritual objects **in the identity** — the mark, the lockup, the wordmark, the app icon,
  anything that stands for targum itself. A Hebrew letterform may be used as pure form
  there, never as an identity signal. Content surfaces are a different question and the
  answer changed on 2026-09-01: see §12.
- Scaling Hebrew below Latin; mirroring a letterform; the accent as body text or a large
  field.

## 11 · Files

The mark, lockup, favicons and app icons live in the design-system project, not this
repository: `assets/` holds `mark.svg` / `mark-dark.svg` / `mark-mono.svg`, `favicon.svg`
(auto light–dark) plus `favicon-16/32.png`, app-icon SVGs and full-bleed PNGs
(1024/512/192, apple-touch-180), `lockup.svg` / `lockup-dark.svg` / `lockup-rtl.svg`, and
mark-512 PNGs.

Lockup SVGs carry live text in the reading-face stack — outline before print use on systems
without Iowan Old Style or Palatino.

In *this* repository: tokens are the `:root` block of
`src/targum/render/assets/reader.css`, which every page carries; the Hebrew reading faces are
`src/targum/render/assets/fonts/`; the enforced rules are `tests/test_brand.py`.

## 12 · Where the code departs, and why

Each entry below was a deliberate decision with a date, kept here so nobody "corrects"
the code back to a rule that was already retired. (The count this line used to give had
fallen behind the entries by half; the dates are the index.)


### The arrival is two questions, a screen each, and the second one is kept — 2026-09-19

The arrival is the one thing a new reader is asked, and until today nothing about it was
written here. It was built under targum-internal#294 and argued over under #306, and the
whole of that lived in commit messages and comments in `learn.js`. It goes here now
because it ends in a departure from a rule this document states twice.

**What is asked.** *What are you interested in?* — nineteen subjects in the words a person
uses about themselves, three at least, every one offered whether or not the shelf can
answer it yet, because three answers are a profile and a profile may name what has not
been filed (#294, 2026-09-17). Then *How much Hebrew do you have?* — the eight rungs of
the ulpan ladder `level.py` climbs, said as what a person can **follow** rather than what
they can read ("I follow slow Hebrew, with help"), because many come to listen and to
watch (#337), with the kitah letter as the smaller half of each row.

**A level was asked, then not, then asked again, and this is the fifth state.** §6 says
engagement counts real things and never a level, §12's "A language with CEFR levels shows
them" says every level shown is *measured*, and `learn.js` has said since it was written
that nobody is asked how good they are. Against that: the measurement happens after the
first text, so the one routing decision it cannot inform is the one a reader meets first,
and a reader at gimel who is handed Scene 1 has been patronised before they have pressed
anything. #306 was closed against (2026-09-17, morning), decided narrowly for — asked,
used once to pick the first text, kept nowhere (2026-09-17) — and decided against again
the next day, because a rung asked and thrown away "stops a reader on their first visit
for an answer thrown away before the page is drawn again: the worst half of both".
David reopened it on 2026-09-19 — "I think we should ask level" — and chose the variant
the card had named and nobody had built:

- **The answer is kept**, on the account beside the subjects, so a phone's answer is not
  asked again on a laptop.
- **It is a seed.** While nothing about the reader has been measured, it decides the
  three things that otherwise have nothing to go on: which text opens first, the band
  the Library opens on, and how hard the conversation writes.
- **It is outvoted by the first measurement.** The moment the reader's own marked words
  reach a rung — by reading, or by the claim grid a minute after the first text — the
  measured rung is what everything reads, and the declared one is not consulted.
- **It is never shown back.** Your Progress shows the measured rung and only that, still
  "A guide, not a placement"; the conversation still never says a level to the reader;
  nothing anywhere says "you said gimel".

So it is a declared level, and the rule it departs from is real. What keeps the departure
small is that the number has a short life and no display: a reader who overclaims gets a
hard first text and is corrected by their own taps within minutes, and nobody downstream
inherits the error, which was the objection.

**One question a screen** (David, 2026-09-19: "one question page", "always clear what
next step is"). The subjects are a screen with a **Next** that wakes at three; the rungs
are a screen where pressing a row is the answer; each says where it is in words ("1 of
2") and each has a **Skip**, because a question a reader may not decline is a gate, and
the arrival is not one. **The last answer opens the text it chose** — the reader, not
Learn with a card to find. On a phone each step is the screen: the subjects wrap as
pills instead of standing as nineteen rows, and Next and Skip are fixed at its foot,
which is the one place a fixed control is right because there is no page under it yet.

This fixes something that was false on a phone. The arrival "sits on the desk ground
rather than in a card… somebody who ignores the question entirely still has a text open
and loses nothing" — true at a desk, where the sheet frames a reader under it, and untrue
under 40rem, where there has been no sheet since 2026-09-14. There, the only filled
button on a new reader's first screen was a disabled one.

**Learn on a phone has one lead.** The cards were "each worth pressing equally" and so
none said *start here*. The first card — Start here, or Continue — is the lead: across
the column, with the one filled button on the page (§13, "filled in the primary, one per
view") and its verb on it. The rest sit under it as they were.

`test_learn_js.py` pins the two steps, the skip, the rung kept and handed back, and the
measured rung outvoting it. targum-internal#334, #306.
### There is one look, and it is light — 2026-09-19

"Remove dark mode everywhere," David wrote, and it is gone: the second palette that
`reader.css` carried twice (once for a browser that prefers dark, once for a reader who
chose it), the chart neutrals `words.css` carried the same way, the switch in the bar, in
the account's sheet and on eight pages of their own, the script in every `<head>` that
stamped the choice before first paint, and the one `localStorage` key that survived a
sign-out.

Half of this was decided three days earlier and never written here. **The front door is
light, always (David, 2026-09-16)** — as `landing.css` recorded it, "one page and one
look. A stranger meeting it for three seconds should not meet a second design because
their phone is in night mode."
That covered the landing page and the pages in front of the door — about, legal, the
holding page — and lived only in their stylesheets and in `test_landing.py`. The argument
did not stop at the door. A second theme is a second design to draw, measure and keep:
every contrast ratio in §4 twice, every shadow tier in §13 twice, a ramp in `words.css`
that had once been written out three times over, and a class of bug — a band that turned
pale on a dark page, a letterbox that became the brightest thing on it — that existed
only because a token could flip. One person draws this, and one look drawn well was
worth more than two kept level.

What is **not** dark mode, and stays exactly as it was:

- **§9's ink inversion** — one block per screen on the ink surface — and the
  max-contrast pair. These are dark surfaces on a light page, and they are why §4 still
  has an "on ink" column: the pale cuts of the accent, the teal and the three functional
  hues are what text and marks are on such a block. The bright set is still ink-panel
  only.
- **A film's letterbox**, the keys over a film being watched, and **the public pages'
  band**. Their colours were literals so that they would not flip; they are literals
  still, because a block that inverts the page should say its own values.
- **The favicon's own `prefers-color-scheme` switch** (§11) and the `-dark` marks and
  lockups. The favicon follows the *tab strip*, which is the browser's and may well be
  dark; the marks are for ink surfaces.

What it cost: a reader who liked it loses it, and a page that is light at night is
brighter than some would choose. Nothing is offered in its place — not a dimmer, not a
sepia. If the reader's page is too bright at night, that is a thing to hear from readers
and answer in the page's own tone, once, for everyone.

**Built readers carry the old theme until they are rendered again.** A reader is one
file with its stylesheet and scripts inlined, so every reader built before this day still
has the dark palette, still reads `targum:theme`, and still draws the switch. The shelf
is rendered again as part of shipping this — rendering, not annotating: no annotator is
renamed and `SCHEMA_VERSION` does not move. Until then a phone in night mode gets a dark
reader off a light desk.

`theme.js` had a second job, where a write goes on a page served over HTTP
(`targumKeep`, `targumForget`); that half is `keep.js`. `sync.js` keeps its keep-list,
empty: the next display preference belongs in it. `test_render.py` pins the absence —
no `prefers-color-scheme` in any stylesheet, no `data-theme` on any page — the way
`test_landing.py` already did for the front door. Five palette entries that only a dark
page used left `test_brand.py`. targum-internal#333.


### The weekly goes out unread, and claims nothing — 2026-09-17

`weekly publish` was the gate the whole design rested on: nothing written by a model went
out under the targum name until a person had read it. §6 said so and every issue said so,
twice — a byline, "Compiled by the targum team", and a notice under the reader, "Compiled
by a model from this week's reporting and curated by the targum team before it went out".

David took the gate out. The reasoning is worth keeping because the trade is a real one:
an issue every week is worth more than an issue whenever somebody had a free evening, and
the weekly had been going out when there was time for it. `deploy/weekly-run.sh` writes,
builds, publishes, announces and ships one on a schedule, and nobody reads it first.

- **Both lines come off the page.** Not softened, not reworded: removed. An issue carries
  its sources at the foot and says nothing about how it was made. The alternative on the
  table was a shorter line saying a model compiled it, and the objection to it is that a
  page explaining its own provenance in one sentence invites the reader to stop there —
  the sources are the honest answer and they are still printed.

  This was raised as a cost before it was chosen, and chosen anyway. It is written down
  here so that nobody restores either line thinking it was lost rather than retired.

- **Issues published before today keep their byline**, because they were curated and the
  line is a fact about them. `BYLINE_HE` and `pipeline.byline_for` survive for exactly
  that, and nothing new is composed with an author.

- **Automatic means nobody reads it. It does not mean nothing checks it.** `publish` still
  refuses a level carrying a source's own wording — that is the licence boundary, and it
  was never waivable — and still refuses a level that missed the band it is labelled with.
  The scheduled run never passes `--anyway`. A run that stops has found something.

Built under targum-internal#316.

### A build is on the shelf while it is building — 2026-09-17

"When I upload something via /add or when I start a build a chat, I need a more obvious
place to see the progress → Notifications tab is too easy to miss."

The bell was not wrong about what it fixed. `building.js` records what it replaced: one
pill, fixed at the foot, showing one build at a time, which could not survive leaving the
page that started it. The panel shows every build, newest first, each dismissable, and it
follows the reader from page to page. What it is not is **findable while you are waiting**
— a corner glyph with a count is ambient, and a build you have just started is the
opposite of ambient.

- **A text being built is a row on the shelf, from the moment it starts.** It appears in
  Your uploads with its title and a line saying how far it has got, and becomes the
  ordinary row when it is done. That is where the reader was going anyway; the library is
  the one page that can honestly say "everything of yours is here", and a text that only
  existed in a notification until it finished made that false for the ten minutes it
  mattered.

- **The page that started it still narrates it.** `/add` already did and keeps doing it.
  The two are not a duplicate: one is where you are, the other is where you go.

- **The bell keeps everything else** — finished builds, followed series, anything landing
  while the reader is elsewhere.

**Nothing new is fixed at the foot of the window.** §13 ends "nothing is fixed at the foot
of the window but the pill", and the straightforward reading of the note was to put the
old pill back and amend that sentence. This does not, and the reason is worth keeping: a
thing fixed over the page is a thing that covers the page, and the reader already has two
of them. Walking away wanted a *destination*, not a second badge, and the shelf is the
destination.

Not in tension with "any notification is fatal" (2026-09-16), which is about pushing at a
reader who is not there. This is a page telling a reader who is there, and waiting, what
is happening.

Built under targum-internal#317.

### A video text opens as its transcript, and a vertical one is vertical — 2026-09-17

This reverses "A video text opens as video" below, which is a fortnight old and came from
the first stranger session. That session is still the evidence, so it is worth being exact
about what it proved and what it did not.

The olah's complaint was that she never found out the page could be heard. What answers it
is that the media is **visible and named** when the page opens. The 2026-09-03 entry went
further — the picture is not on beside the page, *it is the page* — and that further step
is the one being withdrawn. A reader who imported an hour of speech to watch it presses one
key; a reader who came to read Hebrew, which is everybody who stays, was handed a film and
had to dismiss it every time.

- **A text carrying a video opens as its transcript, with the picture docked and on.**
  Reading is the default and watching is one press. The picture is still there, still
  named, still the first thing a stranger can say about the page — so the sentence that
  entry was protecting is kept.

- **The preference is stored the other way up, under a new key.** `targum:video-read:`
  records the departure from the old default — a `1` means "this reader chose to read
  alongside" — and inverting its meaning would shut the picture for exactly the readers who
  liked it. `targum:video-watch:` now records the new departure, and the old key is left
  where it is and ignored, the way `targum:video-open` already was. That mistake has been
  made once on this panel and the file says so.

- **A vertical film fills a vertical frame.** The docked panel and the portrait full-screen
  frame both wrote `aspect-ratio: 16 / 9` into the stylesheet, so a phone video — a Short,
  a reel, anything shot upright — sat in a letterbox with two thirds of the frame black.
  The shape is read off the file itself (`videoWidth`/`videoHeight` when the metadata
  arrives) and the frame takes it. Nothing is fetched to learn it; the element already
  knows. A picture taller than it is wide is sized by its height, or a 9:16 at panel width
  would be a column of video down the whole window.

Built under targum-internal#312.

### The library is browsed, not looked up — 2026-09-17

"Library currently is not usable in my opinion," David wrote, and asked for four things:
a reading at his level, straight away; topics rather than kinds of media; what media a
text has without opening a control; and what was added lately.

The four are one diagnosis. The page is a **sortable table with its filters folded away**,
and that is the shape for somebody who knows what they are looking for. Browsing is the
other posture, and the page had no answer for it. `library.js` is honest that the table
was itself a reaction — to a grid of cards that could not be sorted — and it over-corrected
into a spreadsheet.

What stands in its place:

- **Level is a setting; subject is the navigation.** They were two filters of equal
  weight, folded away together. But "at my level" is not a thing to pick each time you
  browse — it is who the reader is — so it sits in the line above the list, in words, as
  part of a sentence rather than as a filter to be found. The subject is what a reader
  browses by, and it is the visible row of chips.
- **"At my level" is the share of a text's words the reader knows**, not the hard-word
  tier. `difficulty` is a fact about the text — how rare its words are in Hebrew — and
  `known` is a fact about this reader and this text. The second is the question the front
  door sells.
- **And the page never opens on an almost-empty shelf**, which is what makes the setting
  safe to have on by default. Two readers would get one: a stranger, where the fallback
  measure is the text's own hard-word share and the page would be making a claim about
  somebody it knows nothing about; and a reader who has marked a dozen words, where every
  row honestly reads 2% known and nothing is in reach yet. So the default is the narrowest
  band that still leaves a screen's worth, and it widens on its own as a vocabulary grows.
  A reader who *picks* a band gets it whatever it leaves, including nothing — that is an
  answer, where the default is a greeting.
- **A row of chips is drawn from the rows that exist, never from the vocabulary.**
  `Tag` runs well past what is filed, on purpose, because the arrival's doors are drawn
  before the texts are tagged into them. On this page an empty door is a dead end. Hebrew
  carries eight subjects with anything behind them, not seventeen. This is the rule the
  kinds already followed.
- **All is the default, and a subject only ever narrows.** Nearly half the Hebrew shelf
  carries no subject at all (232 of 499 on the day this was written). Subject as the
  primary division would hide them; subject as a filter over everything does not.
- **Each chip carries its count.** The two biggest Hebrew subjects are Tanakh and Judaica.
  Unqualified, a row of subjects tells a modern-Hebrew learner this is a religious
  library; with counts it tells them what is actually there.
- **A text says what it carries on its cover.** Audio and video were a word in a cell and
  a select called Media behind the fold. A mark on the cover is read without opening
  anything, which is the whole of the request.
- **Cards for browsing, the table one press away.** This is the shape the page already
  tried and abandoned, and the reason it failed is answered rather than forgotten: the
  complaint was that a card cannot be sorted, so the sortable table stays, as **List
  view**, and the reader's choice is remembered. Covers exist now, which they did not
  when the grid was first drawn.

The cost, stated: the kinds leave the visible row to make room and go in with the other
filters. That has one consequence worth writing down, because it was found on the running
page and not in a test. The page opens a new reader on the Scenes — the first-visit rule
above — and no scene is filed under any subject, so a subject row computed with the kind
still standing vanished entirely on the first visit of every reader who had it. **The kind
is lifted when the subjects are counted, and pressing a subject clears it.** Picking a
subject is going somewhere, not narrowing where you are; the kind is a refinement inside
the place you were. The number on a chip is therefore what pressing it actually leaves.

Nothing here moves the palette, the type or the desk. Built under targum-internal#314.

### The modern shelf reads in a sans — 2026-09-17

2026-08-29 chose Frank Ruhl Libre for everything outside the Tanakh, and gave the reason
below: "A serif on purpose: these pages are parallel text, and a Hebrew sans beside a
Latin serif reads as two documents rather than one." That reasoning is sound and it comes
from the Latin side of the page.

From the Israeli side the association runs the other way. Shown a modern scene on
2026-09-03, the first stranger to use targum — an olah — said before anything else that
she did not like the font: *"too much like these hard to read Torah fonts they always
use."* Serif Hebrew is the siddur, the Tanakh and the Orthodox publisher's shelf.
Everyday Hebrew — news sites, apps, signage, the ulpan handout — is sans. §1 already
names the Orthodox-publisher shelf as a position deliberately avoided; it named it in
colour, and this extends the same avoidance to type, which is where a Hebrew reader
meets it first.

So **the modern shelf is set in Noto Sans Hebrew** and the Tanakh keeps Taamey Frank CLM.
The mechanism needed no work: the face already follows the text rather than the shelf, so
a modern essay quoting one accented verse still takes the biblical face. Noto Sans Hebrew
is SIL Open Font License 1.1, which permits embedding outright, as Frank Ruhl Libre's OFL
did.

**What this costs, stated plainly.** The 2026-08-29 argument is not wrong, and it is now
being overridden rather than refuted: a Hebrew sans beside a Latin serif genuinely does
read as two faces. The judgement is that two faces that each belong to their own language
beats one face that makes the Hebrew look like liturgy — because the reader whose Hebrew
this is notices the second thing and not the first.

**Decided against this card's own gate.** targum-internal#169 said: "ask the next two
Israeli-Hebrew readers the same open question, unprompted. One person's phrase is not a
rule; the same phrase from three is." Those two were never asked. David decided on one
reader's phrase on 2026-09-17 rather than wait. Recorded here because a decision taken
ahead of its own evidence should say so, and because if the next Israeli readers like the
serif, this is the entry to come back to.

### The interface speaks Russian — 2026-09-15

Every word the product says to a reader now comes from `src/targum/strings/<code>.json`
(targum-internal#184), and Russian is the first catalogue filled (#185). David decided
the following the same day; they change or add rules, so they are recorded.

- **The Russian was drafted by a model and shipped.** No review gate: a reader who
  reports a bad line gets it fixed. A native ear still owns the voice.
- **The name stays Latin and lowercase in every language.** «targum — это
  интерактивный двуязычный текст», never Targum and never таргум, because the wordmark
  it names is Latin (§3). `test_brand.py` holds every catalogue to it.
- **Which rules are universal.** No exclamation marks, no emoji, the name as above, and
  every `{blank}` the English has. `test_brand.py` checks them in every language.
- **Which rules belong to a language.** Terseness and the voice (§6) were written for
  English. Russian runs longer and reads a bare statement as curt, so a Russian line
  may take the words the register needs. That is judged by ear, not by test, with
  one exception: a label (three words or fewer, no closing punctuation) may run to 1.6
  times its English or six characters more, whichever is larger, because the button
  it sits in was sized against the English.
- **A desk page says its own language.** Learn, Library, Progress, You, Add, the lists,
  the conversation and the public pages carry `<html lang>` of the language their words
  are in. A reader and its contents page do the same for their chrome: `<html lang>` is
  the language the chrome's words are in, which is the first rendering's where it has a
  catalogue and English otherwise. The text keeps its own language on `data-language` and
  on every source cell, as the entry below says.
- **A visitor is spoken to in their browser's language.** Signed out, a public page
  takes the first `Accept-Language` that has a catalogue; signed in, the interface
  follows the one language the account reads besides English.


### The Hebrew-first audit — 2026-09-14

David asked for a complete review of the product with the Hebrew learner as its user,
and then for every finding to be fixed. The review is the artifact
https://claude.ai/code/artifact/bf361ca0-73da-4d73-8ddc-1958f1f602a4. Most of what it
found broke rules this file already states — Hebrew in a fallback face, Hebrew scaled
below Latin, `left`/`right` where the desk meant the end — and those were simply fixed.
These are the ones that change or add a rule, so they are recorded.

- **Hebrew is isolated where it meets English, and every field takes its own
  direction.** Every text field is `dir="auto"` with `unicode-bidi: plaintext`; a title
  clips on its own isolate, never on the LTR box around it; plain text that carries a
  Hebrew title (a mail subject, a tab title, a notification) wraps it in U+2068 … U+2069
  and leads with the English. Inside anything tagged Hebrew-script, `--reading` and
  `--chrome` are the Hebrew stack, so a component names its face by variable and never
  has to out-specify the `[lang]` rule.
- **A reader page is English chrome around a text.** `<html lang="en">`, the direction
  still the text's, the text's language on `data-language`, and `lang` on every source
  cell as before. A speaker's name is 0.8125rem in the reading face and is heard by a
  screen reader.
- **The translation language has one name: "Translations in".** On You, Add and Your
  Words, and the first visit asks about translations rather than answers. Every
  language list shows the language's own name after English's, and the language menu is
  headed "You're learning", because it changes neither the interface nor the
  translations.
- **The conversation knows how to address the reader in Hebrew.** You carries "In
  Hebrew, targum calls you" — אַתָּה, אַתְּ or Either — kept on the account and said in
  the ledger. Without an answer the model uses forms that do not choose, and it never
  changes the gender of the reader's own words in a recast: a man's רוצה had been
  "corrected" to רוֹצָה.
- **A Library row says how long before it builds.** The first press prices the text
  and a Start reading beside the row is the spend, as the conversation's card and the
  Add page already had it (see "Add is one box" below).
- **A followed instalment is news for ten days.** After that it is the current issue,
  in the bell and in Learn's sheet, whatever this browser has seen.
- **Names on the Library.** The difficulty column is "Hard words", because it counts
  words rare in the language rather than words new to the reader; the register column
  and filter are "Which Hebrew"; the tabs are All texts and Your uploads. The weekly's
  top edition is "Native": the other two are real Hebrew too.
- **Delete account stands on its own row, in clay, and its second press offers Keep
  my account.** A deleted account signs the browser out and empties its store.
- **Breakpoints.** A `min-width` at 60rem is written 60.01rem, as `reader.css` already
  did once, so a 960px window is one layout and not two at once. The reader's own
  `main` padding and its drawer-as-sheet belong to `body.reader` only.
- **An address that is not a page answers 404, with a page.** It had answered "Coming
  soon" with a 200.

What it does not overturn: "targum" as the name of a built text, the pages on a phone,
the brown-to-leaf ramp on Your Progress, the monospace counts (§5), the reader's
glyph bar (§7), the teal tint on the reader's own conversation lines (§13, phase 2) and
the sheet's "Read here, or go full screen." Each was raised in the review and each is a
decision already recorded here or in a test.


### The picture can be picked up — 2026-09-13

The entry below dated 2026-09-03 said *the picture is never dragged; it docks*, and
argued that a corner solves for good what a drag solves once. David reversed it. It is
the third time a draggable picture has been asked for, this time by the owner directly,
and a rule that has to be defended against the same request three times is a rule the
people using the page are not agreeing with. The
corner answers where the picture may not stand; it does not answer where the reader
wants it, and those are different on every screen and every text.

- **On a wide window the picture is moved by its grip, anywhere in the window**, and
  clamped so it cannot leave it. The grip is a key in the picture's rail, not the frame:
  the picture itself is the play button, and a press on it stays a press. While a
  pointer holds it, it follows the pointer and nothing else (the 2026-09-04 rule); the
  page is laid out again when it is let go of. The arrow keys move it for a keyboard.
- **It is sized from a corner**, the one across from the corner it is held by, keeping
  the picture's shape, between 260px and nine tenths of the window, and never taller
  than the window.
- **Docking is still the default and the start.** A text opens with the picture in the
  reader's corner; the first press of the corner key puts a picked-up picture back
  there and forgets the place. The size survives a dock.
- **A picture put somewhere floats and takes no room.** `room()` stops cutting the pages
  around it, because the reader chose what it covers, and cutting the pages around their
  choice would move the words away from where they put it. This is the one place the
  rule "a control fixed over a page of text takes its room out of the layout" gives way,
  and it gives way only for a place the reader set by hand.
- **Place and size are kept per device**, like the corner, as fractions of the window,
  so a smaller window still has the picture on it.
- **Not on a phone.** Below 60rem the picture is full-bleed in the band and pulled down
  to close; a drag would be a second meaning for the same thumb, and there is nowhere
  else for a full-width panel to stand. Phones keep the two docks. A place kept on a
  wide window waits there for the window to be wide again.

The corner key's name changed with it, from "Move the picture" to "Put the picture in a
corner", because "Move the video" is now the grip's, and two controls answering to the
same name is one name too many.

### The streak is the longest one, and the current one is refused — 2026-09-03

§4 gives `--sun` to "streak milestones, the daily spark", and #34 specified two streaks,
current and longest, when it built the day-activity record. Only the longest is built
(targum-internal#175, built 2026-09-07), and the current one is not unbuilt but refused.

The pull of a current streak comes from the fact that it can be destroyed. That is loss
aversion, the mechanism that makes people play chess at three in the morning — and the
same mechanism that makes them quit for good in the week they break a long one. For a
reading habit measured in years rather than sessions, that trade is bad. A longest run
has none of it: it can be tied or beaten, never lost. It is a count that only rises,
which is the property the whole ledger is built on, so a reader who disappears for a
month comes back to a record intact rather than to a ruin.

So `charts.js` has `longest()` and no function for the run in progress or the gap since
the last reading day; /progress shows the longest quietly beside the other counts; and
it is announced only in the delivered increment at the foot of a finished section, on the
day it rises and on no other, because a longest run never changes except on the day it is
good news. §6 still governs the day chart around it: a missed day is quiet, in the
resting colour, never red. `test_brand.py` pins the absence.

The same entry records the delivery itself: the ledger's increment is put at the foot of a
finished section — the delta, then the standing, for the counts that moved and no others,
in the ledger's treatment, in the flow, with nothing to dismiss and nothing in motion —
because a rating put in front of a reader unbidden is the half of the mechanism that
works, and /progress is a destination.


### Add is one box, for any medium — 2026-09-13

Asked the same day how the Add page could be "more AI native and user friendly, whilst
still allowing users to do manual uploads", and then that it "should be truly media type
agnostic (texts, videos, podcasts, audio notes, etc)". The page was a form: three boxes
to choose between (a file, a link, the text), a Translation toggle, a Transcript toggle
for a recording, and two language pickers, all asked before targum had looked at what
was brought. A stranger had already called the product work (2026-09-03), and this was
the page where that was most true.

Decided, on the preview
https://claude.ai/code/artifact/c1181c3b-1d29-4fa3-ae1f-4b7fd475c838:

- **One box.** It takes a dropped file, several files, a pasted link, pasted Hebrew, or
  a sentence saying what the reader wants. It never asks what kind of thing it was
  given; a line under it says what targum thinks it was, as it is typed.
- **Any medium is the same act.** A book, an article, a podcast episode, a recording, a
  voice note, a video, a subtitle file, a photo of a page: each becomes Hebrew with its
  English beside every line, with its media under it where it has some. The page names
  the medium on the card; it never makes the reader pick one first.
- **What was found, before anything is asked.** A card says what targum read — the
  length, whether a person wrote the subtitles, whether an episode brings its own
  transcript, how much of an article is Hebrew — and puts every decision on one line
  that ends in **Change**.
- **Change is the manual page.** Every control the form had stands behind it, rows that
  do not apply to the medium hidden rather than greyed, open for whoever opened it last.
  Files that belong together are paired without asking — a recording and a subtitle file
  of the same name, a text and its translation in the other script — and the toggles
  return only where the pairing cannot tell.
- **The language is still not guessed.** The page stopped offering "work it out for me"
  because a reader cannot check a guess on a build they are about to pay for
  (`test_the_upload_page_does_not_offer_to_guess_the_language`), and that stands: the summary line names the language the reader last chose, where they
  can see it, and Change is where it is changed. Hebrew, Yiddish and Aramaic share a
  script, so a script could not decide it anyway.
- **Only a description reaches the model.** A file, a link or Hebrew is priced with no
  model at all. A sentence in words is a turn of conversation, is metered like one, and
  the line under the box says so before it is sent. The model finds and prices; the
  reader presses. Its results mix media, because the medium was never the question.
- **The library answers first**, while the words go in, and a refusal says what to do
  instead (a scanned PDF can be read as pictures; a locked link can be looked for
  elsewhere, as an offer, never run unasked).

What it does not overturn: the price before any spend, the model never pressing,
`Library.claim` as the one door, the Add page's reason to exist beside the `+` on the box
(the `+` brings a file while asking; this page is for everything else), and §13 for how
it looks. Other video sites than YouTube are a separate question, not part of this.

### Add is a place again — 2026-09-13

The entry of 2026-09-06 below took Upload out of the nav and made it the `+` on the box,
with the Add page as the card's "More options". Since 2026-09-11 the box lives in a
drawer, and the page it was a door to had no door of its own: a reader who wanted to
bring a text of their own, with a translation or a transcript beside it, had to know to
open the conversation, press `+`, choose a file and then find "More options" — or to
type ⌘K. Its maker asked for the Add page to be reachable from the main navigation, "in
a sleek way".

So the nav is four: Learn · Library · Your Progress · Add. Add is last because the order
is how often somebody wants each one, and bringing a text is the rarest of the four. It
is drawn as the other three are — a pill, current in the primary on its own page — and
is the one place whose glyph, a `+`, stands beside its word at a desk as well as over it
on a phone, since the `+` is how the product already says "bring something". On a phone
the bar at the foot takes four columns. The `+` on the box stays: it brings a file while
asking, and the page is for everything else.

### Anybody can speak to targum, and the sheet says where to read — 2026-09-14

Two things David noticed on the same morning. First: "there is no little microphone to
press inside of the chat. This is important. People should be able to talk to targum, and
this should work on both desktop and mobile and on any other device." Speak had been
offered only in a Hebrew conversation, to a reader with modern Hebrew. Since the language
menu (2026-09-13) every other language opens its own conversation, so most conversations
had no microphone at all, and nor did a reader of scripture. So Speak is in every
conversation now. A conversation held in Hebrew is written down as Hebrew; any other lets
the transcriber recognise what was spoken, so a reader of Italian can ask in Italian or in
English. A browser that records records in place. On one that cannot, the press opens the
device's own recorder, and the clip goes up the same way. A spoken line carries what a
typed one does: the conversation's language, and where the reader is in a reader. The box
names that language too: an Italian conversation still said "Write in Hebrew or English".

Second: on Learn "it should be clearer to the user that, while they can comfortably read on
that page, and we do want it to be comfortable, for the best experience they should click
Open and go to the reader page." The sheet's press was a small "Open" at the end of its
head. It now reads **Open the reader**, with the expand corners a window is made
full-size by, filled in the primary at control height. One line beside it says both
halves: "Read here, or go full screen." That line stands only
over a framed reader, beside the press at a desk and over the known share on a phone.
Nothing about the sheet's comfort changes: it is still the reader, working, at the place
it was left.

### The picture's keys say what they do — 2026-09-14

David, looking at a docked video: the controls "don't make it obvious you can drag it or
resize it", and full screen "it's not obvious you can minimise, and it's not obvious how
to go to the transcript". Four glyphs in a column beside the picture were the whole of it.
So the keys carry their words, the way the box's actions already do (§7). At a desk the
docked picture has a bar across its top: **Move**, a grip that fills the bar so the bar is
the thing to take hold of, **Full screen**, the corner and ×; the size handle in its corner
is drawn on a raised ground instead of a faint hatch. Full screen, the two keys are pills
over a dark backing: **Transcript**, which shrinks the picture to its corner beside the
text, and **Close**. On a phone nothing moves or resizes, and the sheet is unchanged.

**And the reader's own keys, 2026-09-19.** The bar's `?` was §7's typed character "as
itself", and the first stranger read it as what a `?` in a corner means everywhere else:
help. She pressed it to be told how the page works and got a table of keyboard shortcuts.
So it says **Keys**, the word the card it opens already has at its head. The `?` key
still opens it, the card still lists `?`, and the button keeps the mark in two places:
behind ⋯ on a narrow window, where the row is already named Keys, and between 60 and
75rem, where the bar has no room for a word (measured: at 1100px it cost a second row). What a
stranger was actually looking for is not a help page; it is the first ten minutes
(targum-internal#335). targum-internal#338.

### The language menu carries flags, and the date follows the language — 2026-09-14

§1 says "no flags" and §10 lists "flag imagery — texts, not countries" among the things
targum never does. David asked for a small flag beside each language in the menu, and
this is the one place that rule now gives way: the language menu, and nothing else. The
flags are drawn, not typed — an emoji flag is an emoji, which §6 still refuses — at the
size of a word's cap height, with the smallest corner the scale has and a hairline round
the white stripes. They are painted in their own national colours, which are not the
palette's and are not meant to be: a flag recoloured into brand neutrals is not the flag.
Hebrew wears Israel's. Yiddish and Aramaic have no country, and wear language flags David
chose the same day: for Yiddish the white flag with two black stripes and a menorah that is
the proposal most often flown for it, and for Aramaic the Jewish Babylonian Aramaic
proposal, two blue stripes round the gate from the Vilna Talmud's title page, which at this
size is drawn as the gate's outline. A language with no flag keeps its width so the names
still line up. Everywhere else, the rule stands: no flag on a shelf, a
card, a text or the identity, because a text is still not a country.

The same day, the date under the greeting stopped being Hebrew's in every language. It
gives the Hebrew date for Hebrew, Aramaic and Yiddish, whose texts keep that calendar, and
the week's portion with it. For French, Italian and Russian it gives the date the way that
country writes it, in its language, with the public holiday when today is one — fixed
dates and the ones that move with Easter, Western for France and Italy, Orthodox for
Russia. Nothing else there moved: one line, the reader's own date first.

The greeting over it is said in that language too, in Latin letters (2026-09-14, David):
Boker tov, Shalom and Erev tov on Hebrew rather than Good morning, so the first words on the
page are ones a reader can say before they can read the script. Yiddish says Gut morgn, Gutn
tog, Gutn ovnt; Russian Dobroye utro, Dobry den, Dobry vecher; Italian Buongiorno until the
evening and then Buonasera, and French Bonjour and then Bonsoir; Aramaic Tzafra tava and
Ramsha tava, and Shlama, peace, in the afternoon. The English is the line's title. Still the
time of day and nothing else — no Shabbat shalom on a Saturday.

### A language with CEFR levels shows them — 2026-09-13

§6 says engagement counts real things and never shows levels, and Your Progress already
departed from it once: Hebrew's ulpan rung, shown as "A guide, not a placement." Every other
language got milestones only, on the ground that a ladder hung off a Russian word list
"would be a score with a letter on it". David decided the opposite for a language that has
a real ladder of its own: **French, Russian and Italian show a CEFR level, and Hebrew shows
its ulpan rung with the CEFR equivalent beside it** ("ב+ bet plus · about A2+"). Yiddish and
Aramaic keep the milestones, with one line saying why: there is no frequency table to
measure a vocabulary in either against.

What makes it not a score with a letter on it is that the measure is the one the research
ties the levels to, and the page still says it is a guide. The CEFR is climbed by known
words among a language's commonest five thousand or so — Meara and Milton's measure — with
each level starting halfway between the mean vocabularies Milton and Alexiou (2009) found
for learners of French at that level and the one below: A1 at 250, A2 at 1,350, B1 at
2,000, B2 at 2,400, C1 at 2,750, C2 at 3,300. **Measured for French; Russian and Italian
borrow the figures** until a study covers them, and `level.py` says so. "The commonest five
thousand" is read off the bands a word already carries: the 5,000th form in wordfreq sits
just above the Zipf cut where "moderate" ends in all three languages, so nothing new is
generated or shipped. The ulpan's CEFR equivalents follow CEFR-aligned Hebrew teaching,
which treats aleph to vav as roughly A1 to C2.

What does not move: **a word's band is still not a CEFR level.** A band describes a word
and a level describes a reader, and `annotate/base.py` goes on refusing to call band 3
"B1". The distance line counts words, never points ("Another 100 common words to B1."), the
chip is the one celebration a screen allows, and the chat, told the reader's level so it
can grade what it writes, still never tells the reader what level they are.

### The chrome gets a system of its own: the desk — 2026-09-11

Shown the front page after a night of building on it, its maker said: "there might be a
fundamental issue with our design language. For the UI, we are trying to use the same kind
of e-reader inspired language as in the reader. The result is that the UI looks like a wall
of text, as opposed to an interactive app." He was right, and the cause is §5's first
sentence: "the wordmark face is the reading face — the brand is the page." That rule was
written for the reader, where it is right, and the chrome inherited all of it — the serif
on every heading, hue rationed to 5%, hairlines for surfaces, typed words for icons — so
Learn, the conversation and the library read as more pages of the book, with nothing on
them that looks pressable.

Decided the same morning, in order: the reader and the chrome are **two related
languages** — the page and the desk it lies on; the thing to remember is **the text with
its English beside every line**, so the chrome is a quiet frame that gets you into one;
the chrome speaks in a **sans**, the serif kept for a text's own words; things sit on a
**desk**, cards lifting off it; the app takes **a primary colour of its own**, deep teal,
the one cool hue in a warm product, because the brown accent whispered as a control; the
front page opens with **the text to read and the box side by side**, text first on a
phone. Three risks taken on purpose: the text drawn as **a sheet** lying on the desk with
its first lines; the header as **the ink bar**, the screen's one inverted block; and **a
face of the chrome's own**, Source Sans 3, self-hosted, where §5 had chosen system-ui.
The rules are §13. The preview they were decided on:
https://claude.ai/code/artifact/088d173b-b539-4003-bbdb-268823c30219.

What it does not overturn: everything about the reader. §1's page, §4's hues and
their finish, §5's reading faces and bilingual parity, §7's glyphs, §8's reach, and every
reader entry above stand as they are. The reader fetches nothing, so it keeps
system-ui for its bar and never loads the chrome's face. `test_brand.py` widens its
palette, its type scale and its face allowlist by exactly what §13 names, and nothing
else; where a chrome page still carries a reader rule, the chrome rule wins.

### The desk grows up — 2026-09-11

Shown the desk after a day on it, its maker said: "the whole design feels clunky, like
it's from 2016 not 2026." He was right, and what dated it was not the palette, the face or
the voice — those stay — but the grammar it had inherited from §8, written for the
reader: a hairline around every box, corners at 4–8px, controls at 13px with a word in
each, a small-capitals label over every section and column, and nothing that moved.
Decided, in order: the bar is **glass** rather than ink; the phone gets a **bottom bar**
for the three places; corners go to **16 for cards and 24 for sheets**; and the reader's
own chrome — its bar, word card and keys, never the page's lines — follows as a fifth
phase. The plan, with the diagnosis and the page-by-page pass:
https://claude.ai/code/artifact/8408e102-f2aa-4ac3-9da7-3cb2a91ab186.

What this entry changes in the rules: §8's radii and flat-surface bullets now say they
are the reader's page's, and §13 carries the desk's own scale, tiers, tint, glass, three
kinds of button and one curve — and, since the fifth phase, the reader's own chrome
takes them too, its bar on glass and its cards on the floating tier, while the lines of
the page keep §8. `test_brand.py` admits 12, 16 and 24 to the radii and lets a
rule name a corner by its token. What it does not overturn: everything about the reader
— §8 as written still governs the page.

### The front page is named, and answers in place — 2026-09-11

The entry of 2026-09-06 below put one box under the ledger's sentence and sent a typed
line to the conversation page. Shown the page a day later, its maker said what a
stranger would: "this whole design is terribly cluttered, nothing is labeled", "I can't
really tell that it's a chat", "I should not be sent to a new page after making any
prompt", "there is no smooth transition into the next part of the page, just lines",
"remember this is the main front page of the app". So the page is in named parts now.
Under the count, a section called Talk to targum with one sentence saying what it is;
the box; the things most readers ask, each beginning with a verb; and the thread, which
opens in place under them when a line is sent — the conversation page's own script,
run here — in a hairline, because the cards below keep this page's one raised layer.
Under it, Your conversations, named, the last three and a door to all. Then a section
called Read with its own sentence, and the week's issue labelled as this week's. The
parts step down into each other with space, not rules. The conversation page stays,
for the whole list and for a link into one conversation.

*Superseded on 2026-09-11 by §13: the conversation lives on no page, in a drawer opened
from a pill at the foot of every page, so Learn carries no box, no thread and no last
three. Marked 2026-09-15, when David accepted the drawer as the replacement
(targum-internal#235, #237, #238).*

### A silent text can be given a voice, at the reader's press — 2026-09-10

The entry of 2026-09-03 below says a text that carries media opens as its media. This is
its other half, from the notes of 2026-09-10 (targum-internal#246): a Hebrew section
with no recording carries, in This text, one door — "Hear this section" — with what it
costs in the reader's own hours beside it, and nothing else about audio. The press is the
spend, claimed at the estimate and settled to the clip; the section is read aloud a line
at a time so every line has its clock; and the page is written again with the audio in
it, the way an imported recording's is, so it still fetches nothing. Ink for the door,
because it asks the reader to act (§9); the cost in minutes, never money (§6). The door
is drawn only while the voice has a price, and it does not yet: an unpriced voice is not
for sale, which is the decision of 2026-09-10 and the reason the door is not on any page
today.

### The things most readers ask are buttons — 2026-09-10

The entry of 2026-09-06 below cut "starter chips under the box" as a gimmick. From the
notes of 2026-09-10 — "most prompts will be nearly identical, i.e. give me something to
read; we should suggest the top five to seven things to ask; largely a push-the-button
facility with the option of a custom prompt" — they return, and this records the
reversal so it is not argued again.

What is different from what was cut: the chips are drawn from the record and never from
a list. Each stands only where its condition holds — a text in progress, words saved
this fortnight, words marked known, publishers with feeds — so a stranger sees two and
nobody sees more than seven. They stand under the box on Learn and in the empty state of
the conversation page, and never under an answer: follow-up chips after each reply were
cut the same day and stay cut. And the first of them, "Something to read", never
reaches the model: the page asks the server, the server asks the library the way the
model's own tool would, and what comes back is the card — priced, not started, the
reader's press still the spend. The commonest ask costs nothing, which is the cache the
note asked for.

Ink-bordered pills on paper, working controls with no accent (§4); fixed lines, so a
press is the same ask every time; no counts and no level on any of them.

### The list of conversations is a way back — 2026-09-10

The entry of 2026-09-06 below cut "a History sheet" as a gimmick. From the notes of
2026-09-10 — "need a way to navigate to chat history in the UI" — it returns, and this
records the reversal so it is not argued again. What was true on 2026-09-06 was that the
only door to a past conversation was to already be on the conversation page, and on a
phone the list stood under the whole thread and the box, past everything. What the box
made the front door did not give was a way back to what was said through it.

So: a row writes the conversation into the address, and the address opens what it names,
so a conversation can be linked to and the back button goes to the one before. Each row
says when it was last opened, in a person's words. On a phone the list is a sheet behind
an ink pill at the top of the page — the page's one overlay, with the shadow §8 allows
an overlay — and at a desk it stands in its column as before. And Learn carries the
last three under the box, a hairline line in the weekly's shape, with the door to all
of them: not a card, because the cards below have that page's one raised layer.

*The Learn half is superseded on 2026-09-11 by §13: Learn has no box, so it carries no
last three; the way back to a conversation is the list in the drawer and the address.
Marked 2026-09-15 (targum-internal#238).*

What it does not overturn: the list is titles and times, never counts or a level; the
thread stays the conversation page's raised layer; nothing here is a board of doors.

### A picture is read before it is priced — 2026-09-07

Everything else the `+` brings is priced before a cent is spent. A picture cannot be:
until it is read there is nothing to count, no title, no first line, and a card that
said "a picture" would be asking the reader to buy blind. So the reading happens at the
quote, and it is the one spend before a card. What keeps it honest: the file choice is the
consent, the ceiling is thirty pages and is refused at the door before any is read, the
reservation goes through the same claim a build makes and is settled to the receipt,
every picture read is cached by its bytes so a second drop or the build after the quote
reads for nothing, and the card shows the first lines as read and says in words how many
lines could not be read clearly (§6: a count, never a colour). The reader is never shown
what the reading cost, as with every other price here. Scanned PDFs are not read at all
and are refused by name; that is targum-internal#197's, and the reflow-not-facsimile
decision for pictures is recorded there and in #217.

### A conversation is drawn as the text it becomes — 2026-09-06

`/chat` drew a thread: the reader's lines and targum's, the same ink under a quiet label.
In Hebrew it now draws each line as the pair it will be on the shelf, and reads it the
way a text is read: the moment a reply is whole, its Hebrew lines go through the same
lemmatizer a build uses (`chat/record.py`), and each word comes back to the page with its
dictionary form, its band, and whatever meaning the glossary already holds — never one
bought for the purpose. On the page a word takes its state from the reader's own ledger,
read where the reader keeps it: a word marked known is bare; a word still being learned
carries the reader's own dotted line; a word never met is marked in iris, the hue §4
keeps for what is new, and is counted. A name is not vocabulary and is left alone. A tap
on any of them says its dictionary form and its meaning, or offers to look it up, which
is the reader's press and the reader's spend, the same door a word card in a text opens.

The foot of the thread is the record's summary: how long the conversation has run, in the
minutes it is metered in; how many words the reader has not met; what share of the words
they knew. Real counts off the page and the ledger, never a level. Under them, Save as
targum: the reader's own press on the quote the model's save already hands the page, and
still only a quote — the card's button is the spend, as it is everywhere.

Two things were measured before this was built, so nothing here is a hope. A line costs
the annotator about sixty milliseconds warm and a turn about a fifth of a second, against
a nine-second load paid once and warmed when the workers start
(`scripts/measure_line_annotation.py`; the box's own numbers are still owed). And every
turn now records what share of its vocabulary lay outside the words the model was given
(`outside` on the turn): the number the grading claim rests on, kept where the eval can
read it, and not yet a claim anywhere on the page.

What comes back: the words and phrases the reader saved lately ride in the ledger block,
and the model is asked to bring them back where they fit and, once, to ask the reader to
use two — never as a list, never named as an exercise. The research this rests on says a
saved word wants eight to twelve more meetings; the chat-first products the survey looked
at never return one. Only words a newspaper would use come back: a word saved in Judges
that no newspaper uses stays in Judges.

The English under each line is folded since 2026-09-10 (targum-internal#241). "I would
just ignore the Hebrew and read the English": with the English open under every line,
that is what happened. A tap on the pair opens it — the gesture that opens a word's
gloss — and one Show English at the head of the thread opens all of it, remembered. The
recast stays open: it is the reader's own words and the correction. A reader with no
known words sees it all open, because folded Hebrew is a wall to somebody with no words.

The recast says when it corrected (2026-09-10, targum-internal#242). It was always the
correction — the reader's line said the way a Hebrew speaker says it — and it never said
so: it rendered the same whether or not anything was changed, and "do not lecture" kept
the model from saying why. Now a recast that differs from what the reader wrote in
Hebrew is labelled corrected, the words that changed carry a mark, and the model's one
"~ " line — what changed and the rule, one sentence, in the reader's language — is
folded under it and opened by a tap on the pair; open for a reader with no words yet. A
line that was right, or written in English, gets nothing. The body still does not
lecture; a text written from the conversation carries the recast and never the why.
There is no setting for it: the correction-policy setting cut on 2026-09-06 stays cut.

The page is the viewport since 2026-09-10 (targum-internal#247): head, the thread
filling what is left and scrolling inside itself, the box, the foot — so the box is on
screen at any length of conversation. Who said a turn is told by where it stands, the
reader's lines set in from the start and targum's from the end, the same ink on both, with
the name as the turn's label for a screen reader; an answer appends as it arrives, with a
caret; the thread follows the newest line only while the reader was at the bottom; and a
turn fades in over 200ms, or not at all under prefers-reduced-motion. What it keeps: one
raised layer, the thread; the box a hairline field; no bubbles, no avatars, no second
column, no iframe — the shell cut on 2026-09-06 stays cut.

The line under each Hebrew line is in the language the reader reads (2026-09-10,
targum-internal#243). It was English by name in the contract, whatever the account said
it read into. Now the contract names the reader's language, the record's meanings are
looked up in it, and the read-back builds into it. And the first visit asks the one
thing nothing about a stranger says: a browser that speaks a language the conversation
can gloss in — Russian, today — is asked once, in that language, whether the lines
should be in it. Never a silent guess; the answer changes only on the press. The
conversation itself stays Hebrew for everyone, as decided on 2026-09-06 and confirmed
on 2026-09-10 against easing a new reader in through their own language.

The reason is the chat plan's sentence: where a choice is between a better conversation
and a better record, take the record. Drawing the thread as the text is the record made
visible while it is being made, and it costs no second surface. If the thread ever becomes
the thing people look at and the shelf an afterthought, the design has gone wrong in the
way §1 describes.

### The front door is a question — 2026-09-06

Learn opened with two cards and a list: the text you were in, and everything else. From
the note of 2026-09-05 that asked for "the Lovable of language learning", and from a day
of looking at that product — one box on the front page that makes the thing, then a
conversation beside it — Learn now carries one box under the ledger's own sentence, and
nothing else on the page moves. The box takes a request, a link, a file by its `+`, or a
word, and Speak (on every device since 2026-09-14). A line typed there opens a conversation and
goes to it; nothing is answered on Learn. The `+` is the Add page's whole job in one
press: a file, a picture or a recording is held in the box as a chip until Send, goes up
as it did there, is priced, and the card the model's quote draws is a turn in the
conversation, on Learn too, where the conversation page opens on it the way it opens on
a line. Send with a file in the box is the press: the text builds and opens when it is
ready, and a bare file, or a line that only says "open this", starts no conversation at
all — "when I wrote 'open this' with a file, I didn't want that to be the start of a
conversation." A line that says more is a specification: it is said, with a note of what
was sent so the model answers about the text rather than asking for it, and the card
follows it in the thread as the build's progress. "More options" is the Add page, kept
for a translation or a transcript of the reader's own. (Until 2026-09-07 the card stood under the
box on Learn with a button to press: "I'm chatting, I think I should be pressing Send",
and "I originally just gave the file… it should have been enough to just open it".) Chat is no longer a place in the nav and Upload
is no longer a corner: both are the box. The nav is Learn · Library · Your Progress, and
the conversation page marks Learn, the way Learn's own lists do. (Amended 2026-09-13: Add
is the fourth place again, after Your Progress; the `+` on the box stays.)

What was tried first, and cut the same day, so it is not tried again: a board of three
doors under the box (the text to read, a conversation to have, the week's words) that
drew the day as a task list, on a product two strangers had already called work; a
two-column workspace with the reader framed beside the thread; a strip and a sheet on the
phone; a switch between finding and talking ("I do not intuitively understand what this
switcher means"). The research the doors were built on still stands — a saved word needs
eight to twelve more encounters, using a word is worth more than looking it up — and is
served invisibly: the next text is chosen for the words just saved, the week's words are
delivered at the foot of a section, and the words come back inside the conversation from
the ledger block, with no door and no label.

One conversation, always in Hebrew, was decided the same morning. (*Amended 2026-09-13:*
one conversation per language, since the language menu in §13. Hebrew's is exactly as
decided here. A language without a conversation of its own yet opens in the English find
mode described next, and Aramaic stays there.) The one exception,
decided the same afternoon: a reader whose every text is scripture is not written Hebrew
at. Nobody converses in the Hebrew of Judges, and a model writing it graded to a ledger
of biblical words would be pastiche on the one shelf where every line must be right. That
reader's box finds and answers in English, about the text. (*Amended 2026-09-14:* it is
offered the microphone like everybody else; see "Anybody can speak to targum" above.)
Decided from the shelf (`Library.talks`), because the ledger is one bucket
per language and cannot say which Hebrew a word came from.

What it reverses: the `_nav.html.j2` note of 2026-09-05 that put Chat second because
"Learn is where a returning reader picks up, and the chat is where they go when they do
not know what to pick up". A day later the two are one page, and the gate stands: at
thirty days, does the alpha reader open something she found by asking, unprompted? If she
goes to the library instead, the door was not the problem and the box goes back to a page.

One more door on a page that is not this one: the gloss card in the reader gains Ask,
and the answer lives in the card, two turns at most, about the text — what the form is,
why it is that form here — with "Continue in chat" as the way on. (Amended 2026-09-11:
the card's answer was in English for everyone; it is now in Hebrew at the reader's
level like every other line of the conversation, since a note of where the reader is
decides what the answer is about and never its language. Only a scripture-only shelf
still opens the conversation in English.) The reader
stays a reader: full page, nothing beside it, and still fetching nothing — the card talks
to its own origin the way a gloss does today, on the reader's press. Ask is a working
action and takes the accent; the field and the button are in the thumb registry.

What it does not overturn: one raised layer per view (on Learn, the cards; on the
conversation page, the thread — the box is a hairline field on both); ink for the door
that asks somebody to act and accent for Send; no invented currency; counts, never a
level; a text that carries media opens as its media; the reader is a full page and
fetches nothing.

### targum speaks back — 2026-09-05

Until now every surface here was a page a reader looked at. From a handwritten note of
2026-09-05, targum gains a conversation: a reader asks for something to read, asks what
they know, and — in the slices that follow — asks targum to bring a text in, talks to it
in Hebrew graded to their own ledger, and reads that conversation back as a targum. The
roadmap's "not building" line named conversation and tutoring, and the reason it did is
recorded there with the reversal; this section is only about what it does to the paint.

- **The chat page is chrome, not a reader.** *Readers must fetch nothing* governs the
  self-contained files a build writes, and `test_render.py` holds it there unchanged. The
  chat page talks to its own origin — `POST /chat/say`, an event stream back — under the
  same `POLICY` every served page already takes, with `connect-src 'self'` doing exactly
  the work it was written for. Nothing in that policy moved to make this possible, and
  `test_serve.py` pins that it did not.
- **A conversation is the server's.** Words, reading position and days stay the
  browser's, as `sync.js` has always said. A conversation is written server-side because
  the same one has to be resumable from a client that is not this browser, and because a
  chat is not a reader. The asymmetry is written beside the rule it departs from.
- **A chat that knows your words still may not say a level.** The ledger goes to the
  model so the Hebrew it writes can be graded; what the model says to the reader is the
  counts — §6's "12 days reading", "500 words known" — and never "you are at bet". The
  progress page's "A guide, not a placement" is now a rule the prompt carries too.
- **The English is chrome, the Hebrew is content** — see §6.

What this does not overturn: engagement yes and arcade no, the ledger in serif tabular
numbers, no invented currency, the hue budget, one raised layer per view. A conversation
that starts congratulating people has gone wrong in exactly the way §1 describes.

### A thing that moves under a thumb belongs to the thumb — 2026-09-04

A reader on a phone holds the page in one hand and works it with that thumb. They pull
sheets down, they slide them back up, they catch them halfway — not because targum
taught them to, but because every app they have ever used did. The sheets here answer to
that or they read as broken, and "a little bit of a glitch" is all it takes: the reader
does not think *this animation and this gesture disagree about who owns the transform*,
they think *this is not working properly*, and they are right.

The rule: **while a finger is on something, that thing follows the finger and nothing
else does.** Not the animation that was playing when the finger landed, not a relayout,
not the browser's own idea of what the gesture was for. A sheet caught on its way up
stops where it was caught and goes where it is taken.

What this cost, so nobody re-introduces it: a word's card rises over 220ms, and a CSS
animation outranks an inline style, so the transform the drag wrote could not be seen
while `rise` was running. A thumb landing on a rising card was ignored for the rest of
the animation and the card then jumped to catch up — measured on a phone viewport, the
card went 13.5px → 3.1px → 0.2px, *upward, against a finger pulling down*, and then
leapt 60px in one frame. The fix takes the sheet off its animation at the moment of
touch and pins it where the finger found it.

`test_a_sheet_caught_on_its_way_up_follows_the_finger` holds it, and it is the one
browser test that runs with motion **on**: the rest of the suite sets
`prefers-reduced-motion`, which switches `rise` off, so the path every reader is
actually on had no test and this was invisible.

### A video text opens as video, and the picture never floats — 2026-09-03

The section below reversed the default the same day: a text that carries media opens as
its media. It stopped one step short of the thing it had just argued for. The picture came
on, but it came on beside a page of text, in the band, at the size a panel is — which is
what a reader who has just been told *this is a video* does not see.

Two rules, decided together because they pull opposite ways and only settle as a pair.

- **A text carrying a video sidecar opens full-screen as video, its Hebrew and English
  overlaid as subtitles.** This is the mode a reader lands in. Leaving it for the reading
  page is one press and is remembered per text, the same way the panel's own closure
  already is. It is scoped to the sidecar and nothing else: a text with audio, a text with
  neither, and every page of the Tanakh open exactly as they did.

  This amends the last bullet of the section below — *the player and the picture stay
  occupants of the band* — for video only. The sentence was written when the picture was
  a panel and it is right about the panel; it is wrong about a reader who imported an
  hour of speech to watch it. The reading column keeps its measure in every mode the
  reader can be in with the text in front of them, which is what that sentence was
  protecting. It is not protecting a thumbnail.

- ~~**The picture is never dragged.** It docks.~~ *Superseded 2026-09-13, see "The
  picture can be picked up" above: on a wide window it can be moved anywhere and sized
  from a corner, and the dock described here is the default it starts in and the corner
  key returns it to.* Learn mode puts the video in one of four
  corners, the reader chooses which once and it is remembered, and the dock is a resident
  of the band in the sense "A word's card covers the page on a phone" gives that word: it
  takes its room out of the layout, and the reading is laid out around it.

  The note this came from asked for a draggable player, and the reason it asked is real —
  a picture parked over the sentence being read is the whole complaint. A drag solves that
  once, per session, per device, with a thumb, while reading. A corner solves it for good.
  The rule that a control fixed over a page of text takes its room out of the layout was
  settled five days earlier and it survives this: what changed is where the picture may
  stand, not whether the page is laid out around it.

Written from a note dated 2026-09-03. Built under targum-internal #182.

### A text that carries media opens as its media — 2026-09-03

§1 said *the reader is a reader, not a player*, and the 2026-08-31 departure below leaned on
it to keep the video panel shut until pressed. The sentence was written against the
language-app arcade, and for the reader the research corpus knew: the Biblical autodidact
who reads first and listens beside. Both halves were decided before anyone outside the
household had seen a page.

On 2026-09-03 the first stranger — an olah, a designer, the modern segment the corpus had
almost nothing on — was shown a scene that had a recording. She did not find out it could
be heard, and she said the thing the corpus could not: *I like to start with media and
learn from that; this is just a boring text.* That is not one person's taste. It is the
comprehensible-input method, and it is how the modern learner arrives. David withdrew the
sentence the same day.

What stands in its place:

- **A text with a recording opens with the player standing and named.** Not a button in
  the bar to be discovered, and not a strip that reads as chrome: the first thing a
  stranger can say about the page is that it can be heard.
- **A text with video opens with its picture on.** The toggle stays, so the picture can be
  put away; the default reverses. *Carried further 2026-09-03, see "A video text opens as
  video" above: the picture is not on beside the page, it is the page until the reader
  says otherwise.*
- **Nothing plays until pressed.** Autoplay is the arcade's move, and a reader on a train
  is still a reader.
- **A text with neither opens exactly as before.** The Tanakh page is untouched by this.
- **The text is still the page.** The media is how it opens, not what it is: the player
  and the picture stay occupants of the band, and the reading column keeps its measure.
  *Amended for video 2026-09-03, see "A video text opens as video" above: a text carrying
  a video sidecar opens full-screen with its text as subtitles, and the picture is an
  occupant of the band only in learn mode. Audio is untouched — the player is still an
  occupant, always.*

The other half of the withdrawn sentence — engagement yes, arcade no; streaks and goals as
a ledger in serif tabular numbers — is unchanged and `test_brand.py` still enforces it.
Recorded in the vault: *Targum user session 2026-09-03 — designer olah*. Built under
targum-internal #168.

### A word's card covers the page on a phone; it does not move it — 2026-09-03

The band at the foot of a narrow window was built on one rule: a control fixed over a
page of text takes its room out of the layout, never out of the reading. The sheet, the
keys and the video panel still do. A word's card and a phrase's chip no longer do, and
since 2026-09-14 neither does the menu behind ⋯ (below). They are drawn over the page, the strip, the arrows and the sheet, and the page is
not laid out again for them.

The rule was right for the things that stay and wrong for the thing that lasts a moment.
With the card in the band, every tap on a word cut the chapter into different pages
(measured: 60 pages became 80 with a card up and 60 again when it closed), so the words
in front of the reader changed twice for one look at one meaning, and the reader said so
(targum-internal#155): the screen must not move, and the words on it must not change
until they turn the page. A card over the last lines of a page is a card they can pull
down. A page that moves under their finger is not something they can do anything about.

### Learn on a phone is cards, not a reader — 2026-09-14

The morning's decision put the reader itself on a phone's Learn page, framed and working
under the known share and Open the reader, and the same afternoon a floor was added for
phones too short to read in. Using it on his own phone, David reversed it: "the reading on
mobile learn page had to be a card, not an actual reader", and then "maybe we can have
multiple cards on mobile, giving more choice and a more useful and efficient mobile
experience". A reader in a frame the width of a phone is a reader with half of its own
controls over the text, one line or two of it, and the real reader one press away anyway.

So under 40rem Learn draws a card for every text it would otherwise put behind a door: what
the sheet holds first, a subscription's new instalment, the suggestion, the texts read
lately and the ones followed, each once, each the press to its reader, with All your
targums under them. The row of doors goes with the sheet, because the cards are the
doors. A text the conversation offers opens its reader directly, as on every other page.
At a desk the sheet frames the reader across the row. (The doors chose what it held until
2026-09-18, when the desk got the cards too, as a rail beside the sheet, and the row of
doors left it — targum#294. The card whose text the sheet shows is marked in the rail.)

### The menu behind ⋯ covers the page too — 2026-09-14

The same reasoning, one visit later. Opening ⋯ on a phone laid the chapter out again for
the menu's height: Genesis 1 at 375×667 went from 26 pages to 31, and "1 of 31" and the
arrows then sat over the verse being read (the Hebrew-first audit, R-02;
targum-internal#273). The menu is a visit like the card: open it, change a setting or
don't, put it away. So it is drawn over the page, the strip, the arrows and the sheet,
and the page is laid out again only if a setting inside it changes the page, as Type and
"Pages, or one long scroll" do. A tap on the page still puts it away.

### A daily page carries an artefact, not an invented face — 2026-09-01

The daily learning pages take the parasha's band: a seam down the middle, words on the
ink half, a picture on the other. What is in the picture is the decision.

Each cycle shows **something that exists** — the Kaufmann Mishnah, the Aleppo Codex, the
Leningrad Codex, and for Tehillim the sixth-century synagogue floor at Gaza with David and
his lyre on it. What is refused is not a face; it is an invented one.

The line runs between them like this. There is no likeness of Judah the Prince, and every
"portrait" of a sage of the Mishnah is a nineteenth-century artist's guess — printing one
as the hero of a page about his book is a fabrication presented as a fact, and the one
photograph of anything connected to him is CC BY-SA besides, which this shelf refuses
everywhere else and cannot start accepting for a decoration. The Gaza mosaic is the other
thing entirely: a floor a Jewish community laid in 508 and labelled דויד in tesserae, as
much an artefact of how the Psalms were read as a codex is. A picture may be of a thing
and must not be a claim about one. `COVER_RULES` says "no faces" about images a model is
asked to invent, which is the same rule from the other end.

The band was one column here for an afternoon, while the page had no picture, and half of
it was empty black with the headline wrapping inside a column measured for something
standing beside it — which is what a grid built for two things does when it is given one.
Recorded because the fix was to add the picture, not to change the grid.

`assets/manuscripts/README.md` carries the provenance and the licence of each.

### The library folds — 2026-09-01

§9 says one raised layer per view, and the library page's own rule is one row per text in
one list you can sort and sift. Both still hold. What changed is that one row per text
stopped being readable: the Mishneh Torah is thirteen rows of `הלכות …`, Berdichevsky is
thirty-nine stories, the hundred scenes are a hundred, and the Mishnah would be
sixty-three tractates. Three hundred and fifty-two rows is not a shelf somebody browses.

So several texts may now be one row that opens where it stands. It is not a second layer
and must not become one: the collection sits on the same seven-column grid as every other
row, its members line up with everything above them, and what marks them is a hairline
down their leading edge — §9's "if a card needs a card, use a hairline". The disclosure
takes the place of the cover rather than claiming a column of its own, because a column of
its own would push the whole list out of true.

The list stays one list, and the controls still act on all of it: a collection is built
out of the rows that survived the filters, so opening one never shows a text the reader
filtered away, and a search opens what it found rather than reporting one shut row.

### Which Hebrew is five answers, not two — 2026-09-01

The register filter offered Biblical and Modern for as long as the shelf was scripture and
journalism. It was lying to more than half of it. A hundred and fifty-nine entries filed
`modern` were written between 1853 and 1930 — Mapu, Mendele, Ahad Ha'am, Ben-Yehuda's own
journalism, Brenner, Gnessin, Berdichevsky — in a literary Hebrew built deliberately out of
the biblical and rabbinic layers, before anybody spoke the language. The measurement agrees
with the reader: Gnessin comes out at 26–31% hard words against 11–19 for the news filed
beside him.

Five now, and they read oldest to newest: Biblical, Rabbinic, Medieval, Revival, Modern.
Never sorted alphabetically — the field is a ramp a learner climbs, and Modern above
Rabbinic because M precedes R would throw that away. §5's switch was documented for "two
or three answers"; it wraps rather than scrolls, because a filter whose options you cannot
see is not a filter.

### A ritual object may stand on a content page — 2026-09-01

§10 banned ritual objects outright. That was written for the identity, where it still
holds without exception: nothing that stands for targum itself carries a scroll, a
menorah, a crown or a pointer, because the product is a reader for texts and not a badge
for one tradition, and a mark that says otherwise says it on every shelf including the
ones with no Hebrew on them.

A page about the week's Torah portion is not the identity. It is a content surface, about
one text, for somebody who came looking for that text — and refusing it a picture of the
thing it is about was the rule doing a job it was never written for. So on a content
surface a ritual object is allowed, under the conditions the rest of this document already
implies: it is imagery and never chrome, it never enters the mark or the lockup, it is
`aria-hidden` decoration rather than a control, it obeys §9's hue budget, and it never
arrives with the heritage-gold, metallic, bevelled finish §10's first line still bans —
that look is the wrong century whatever it is a picture of.

David's call, recorded here rather than argued in a code comment, and the reason the
paragraph above it now says "in the identity".

### Scripture has a third form of its text — 2026-09-01

A reader shows a sentence two ways: bare, or everything the edition wrote. Scripture now
shows a third — the vowels with the chanting marks taken off — and `/parasha` is why. The
te'amim are the whole point for somebody preparing to leyn and noise on top of the vowels
for somebody still learning to read, and those are the same page.

This is the second time it has been built. The first was a middle step in the vowel switch,
0 to 2, and it went inside a day: three positions on one control is a state to get lost in,
and the word arrows broke on the new form. Neither carries over. It is a **separate
two-position control** — the vowel switch still has its two — and it sits in the ⋯ menu,
where a setting made once by somebody who knows what it is belongs. The arrows work because
the reason they broke was fixed elsewhere in the meantime: `markMap` in `reader.js` derives
a cell's offsets from that cell's own characters, so a form nobody had thought of when it
was written maps like every other. Measured on Ruth: nineteen word spans in both forms,
each carrying its own marks inside its own span.

Every text without cantillation is untouched — two cells, one switch, no second button —
and `test_render.py` holds both halves of that.

**And the page's picture is a scroll.** `/parasha` opens on a band the width of the
window, split down the middle: the words on ink, a photograph of a Torah scroll's columns
beside them. The seam is upright rather than a scrim over the picture, because a headline
set over a photograph *of writing* is a fight whose only win is dimming the photograph
until it stops being one — turning the seam means no word is ever over the picture, so the
type keeps its contrast and the picture keeps its strength. On a phone the seam turns with
the layout and the picture takes the top.

Three things about it are worth writing down. It is §9's one inverted block, spent here.
Its colours are **constants, not tokens** — `#171614`, `#e6e1d8`, `#fffdf9`, `#c8a778`,
every one of them out of §4's table — so the band says its own values. (They were constants for a second reason
until 2026-09-19: the max-contrast pair flipped with the theme, and there is no theme
now.) And the photograph is a stand-in: `assets/scroll/README.md`
says whose it is, that it is CC0, and that a commissioned one is what should ship.

### A reader that carries moving pictures — 2026-08-31

An imported video keeps its pictures, and three rules bend to carry them:

- **The reader folder gains a `video/` sidecar.** The one-file reader stays one file for
  text and sound; a part of video is ten times the whole page, so it is the single thing
  too heavy to inline. It stands beside the file with a relative address — a folder that
  travels to a disk keeps its picture, and the page still fetches nothing from any
  network. `test_render.py`'s no-network rules hold unchanged.
- **The video panel is off by default and toggled** — *superseded 2026-09-03, see "A text
  that carries media opens as its media" above: the picture now opens on.* As written on
  2026-08-31: §1's "a reader is a reader, not a player" stands: the transport is still the
  player strip, the picture is optional, and a reader who never presses the button reads
  exactly the page they had. On a narrow window the panel is an occupant of the band like
  the sheet, the keys and the menu, one at a time; the word cards are drawn over it (see
  "A word's card covers the page on a phone" above).
- **The serve policy's `media-src` gains `'self'`** — for exactly these sidecars, and
  nothing else. The embedded recordings stay `data:`; no address leaves the origin.
- **A video fetched from YouTube links home, at the line being read** (2026-09-02).
  The bar gains one link beside the video toggle — the only control in it that is a
  link — opening YouTube's own page at the second the sentence in front of the reader
  starts. It is drawn as its neighbours are and is second to the toggle: the sidecar
  plays on a plane and the link does not. It appears only where there is a home to go
  to; an uploaded file has none, and a dead "open the original" is a control that
  lies. `test_render.py` pins the address as the third outbound allowance, beside the
  conjugation tables and the licence, each with its reason written next to it.

### The weekly landing carries the press — 2026-08-31

The weekly landing page needed to read as news at a glance, and nothing in the identity
says news. Two things now do, and both bend rules written for targum's own paint:

- **Third-party press marks appear in their own colours.** The hero carries "From this
  week's reporting in" followed by the wordmarks of the outlets the issue actually cites
  — and ynet's is red, walla's is orange. §4 and §10 ban those hues for *targum's*
  identity and interface, and still do; an outlet's mark in an outlet's colour is that
  outlet speaking, not us. The marks are nominative attribution, sized to the text
  around them, only ever for outlets cited in the issue on the page. They live in
  `assets/press/` with their licences recorded beside them.
- **The hero's newspaper stack is imagery, and imagery may sit up.** Beside the pitch,
  a small stack of photographed Israeli front pages carries the §9 gloss recipe and the
  `--lift` shadow although it is not a floating overlay. §8's "shadows exist only on
  floating overlays" governs surfaces the interface rests things on; the stack is an
  illustration of an object that casts one. It is `aria-hidden`, square-cornered (a
  newspaper has no radius), printed as it was printed, and never
  carries controls. The photographs are not free files — a front page is a copyrighted
  work — and shipping them was David's decision, made knowingly on 2026-08-31;
  `assets/press/README.md` records which files and what to do if an outlet objects.

### Calls to action are ink, not accent — 2026-08-31

§9 used to give "accent links and primary buttons" one treatment. The accent's calm is
its whole point inside the product, and exactly wrong on the one button a stranger has
to notice: on warm paper, `#7a5c38` whispered. The palette already held the strongest
move it owns — §9's max-contrast pair — so a call to action takes it: ink-filled, paper
text, weight 600, paper-on-ink inside an inverted block. Working buttons inside the
product keep the accent; nothing else moved.

### A landing page has a headline the reader never needs — 2026-08-31

§5's scale topped out at display 1.75rem, which is right for a page somebody reads and wrong
for the one page that has to be read from across a room. `/weekly` is a stranger's first
introduction to targum, and its headline was the size of a chapter title. The scale gains a
**landing display** step — 2.75rem, 2.25rem on a phone — for the single headline of a public
landing page. It does not appear inside the product, and `test_brand.py` allows it only
because this paragraph exists.

### The knowledge ramp climbs to leaf, not gold — 2026-08-28

§4 described four gold steps for the chart ramp (`#c8a778 → #ab8555 → #8b6840 → #6b4f2e`).
The code stopped painting them: gold on warm paper made every chart on the page read brown,
and §4 gives "known" to leaf by name. The ramp is now tints of `--leaf` mixed against
`--paper`, so "known" is the
most present step on each.

**The structure §4 asks for is unchanged** — one hue, monotone, four steps, the end nearest
the surface clear of it, "known" carrying on both surfaces. Only the hue moved.

### The Hebrew reading face is carried, and there are two of it — 2026-08-29

§5 said the reading stack was Latin-first with `Taamey Frank CLM → Frank Ruhl CLM → SBL
Hebrew` appended, "so nikkud never falls to a platform default." That intent is right. The
mechanism was not, and it failed twice.

**First, appending was slow.** Every pointed Hebrew cluster walked four Latin faces before
reaching one that could carry it, and a base letter with its marks is one cluster to
resolve, not one character. Measured on the Declaration: 901ms to first frame against 5ms.
The reader was not slow; the page could not be laid out. Hebrew got its own stack.

**Second, naming a font is not having it.** None of Taamey Frank CLM, Frank Ruhl CLM or SBL
Hebrew ships with a stock operating system, so every reader fell through to New Peninim MT —
which cannot draw one of the 31 Hebrew accents, nor meteg, paseq, sof pasuq or qamats qatan.
That was invisible while the Tanakh arrived with its accents stripped out. The day it arrived
whole, every accented letter was borrowed from another font, and WebKit substitutes the whole
cluster, so the letter changed size too. A verse came out in two fonts at once.

So targum carries its own, one per register, embedded in the page:

- **Taamey Frank CLM** on the Tanakh — cut for pointed and accented scripture; its accents
  are designed rather than tolerated, and its letters hold one size. Taamey Ashkenaz, beside
  it in the same collection, does not: its shin, mem and final mem draw visibly larger than
  their neighbours, which on a page of verses reads as broken text rather than as a face. Koren Type is the face this shelf would want and it
  is © Koren Publishers Jerusalem, so it is not an option at any price; this is the nearest
  a licence allows.
- **Frank Ruhl Libre** everywhere else — a modern cut of the Hebrew book serif. A serif on
  purpose: these pages are parallel text, and a Hebrew sans beside a Latin serif reads as
  two documents rather than one. **Superseded 2026-09-17: the modern shelf is set in Noto
  Sans Hebrew** — see the entry of that date. The two-face mechanism below is unchanged;
  only which face is the modern one moved.

**A font a page merely names is a font some readers do not have.** Each page inlines only
the face it needs — and which face it needs follows *the text*, not the shelf: a modern
essay that quotes one accented verse takes the biblical face, because the modern one has no
accents in it and a page must be able to draw its own text. `test_render.py` checks the
biblical face against the whole Masoretic repertoire and the modern one against everything
a modern text can hold.

**A third failure, from the fix itself.** `:lang(he)` matches an element's *inherited*
language, so `<html lang="he">` handed the Hebrew face to `<body>` and every wrapper below
it, outranking the `font-family` on `body` — and the English translation column inherited
it. Harmless for as long as the Hebrew stack could not draw Latin at all; the day the page
carried a Hebrew face with Latin glyphs of its own, every translation on the Tanakh shelf
was set in them. The rule matches `[lang|="he"]:not(html)` now: what declares itself
Hebrew, and not the page around it.

Two more consequences worth keeping: the faces are `font-display: block`, and `reader.js`
re-measures on `document.fonts.ready` — a page paginated in a fallback's metrics puts its
last verse outside the window. Taamey Frank CLM is GPL v2 with the font-embedding
exception and Frank Ruhl Libre is OFL, so a reader carrying either is not itself GPL. That
exception is per author rather than per project, and the Culmus collection is mixed — Taamey
David CLM sits beside the others without one — so `assets/fonts/README.md` says how to check
a candidate before shipping it.

**A fourth failure, and the one that reached a reader.** `targum serve` sends a
Content-Security-Policy of `default-src 'none'` with a `data:` exception for images only.
Fonts fall under the default, so the embedded face was refused by policy on every served
page: `document.fonts` reported it as an error and the text fell through the stack to a face
with no accents — the original bug, back. Every check had opened the file directly, where no
policy applies, so every check passed. The policy now names `font-src data:`,
`test_serve.py` pins it, and the lesson is recorded here: **a reader is checked the way a
reader is served.**

### targum talks to the reader, as "we" — 2026-09-13

Until today the product described itself in the third person, in a literary register
("A link. targum reads what is there before it gives a price."). David asked for copy
that talks straight to the reader and is a pleasure to meet — "Thanks for the link.
We're estimating how long it'll take." — everywhere. §6 now says so: "we" to "you",
thanks for what the reader brings, what we are doing now and how long it will take.

What survives from the terse voice below: short lines, one- or two-word buttons, no
exclamation marks, no emoji, the lowercase name, no invented currency, no superlatives.
What does not: the third-person narrator and the refusal to soften. Price language left
the product the same day — the reader pays by the month, so a wait is a time and a cost
is hours.

### The voice is terser than "reasons given" — 2026-08-24

*Partly superseded on 2026-09-13 by the entry above: still short, no longer impersonal.*

§6 asks for complete sentences with "reasons given", which is what produced 131 words on a
sign-in page. David cut that by half and the terser reading wins. Reasons are still given
where a reader would otherwise be confused about a limit, but not as a default shape for
every message.

## 13 · The desk — the chrome's own system

The reader is the page. Everything around it — Learn, the conversation, the library, Your
Progress, the account, the Add page — is the desk the page lies on, and is built to be
operated rather than read. Added 2026-09-11; the reasons are in §12. The pages in front of
the door — sign-in, the holding page and its 404, What's built — stand on the desk too
since 2026-09-14 (targum-internal#276): the ground, the chrome's face, the door and the
count as cards, the address in a well, and the call to action still ink (§9).

**Surfaces.** The ground of every chrome page is the desk, `#ece7de`;
things sit on it as cards, `#fffdf9`, raised by their shadow and not by
a line: three tiers — rest `0 1px 2px` at 6%, raised with `0 8px 24px -12px` at 18%
under it, floating with `0 24px 48px -20px` at 28%. A hairline, ink
at 8%, stands only where two same-tone surfaces meet. Two more surfaces: **tint**, the
primary at 9%, which is the ordinary press; and **glass**, the card at 78% under a 12px
blur, which is the bar. The one pure-paper surface, `#fbf9f5`, is the reader's page
— and, on the desk, the sheet: a text drawn as itself — the reader, framed and working,
at the place it was left (`?preview=1`: it draws no bar, keeps its own links in the
frame, sends every other link to the page, and counts a visit at the first press rather
than at being shown), its title, Expand and Open under it — a shadow offset `2px 3px` as
a page casts, no card chrome. The header is glass (decided 2026-09-11; it was the ink bar, `#171614`, for a
morning): sticky, no rule under it, the places as tint pills with the current one in the
primary, the bell and the account as round buttons; the reader keeps its own bar. On a
phone (under 40rem) the four places — Learn, Library, Your Progress, Add — are a bar at
the foot of the window on glass, a glyph over each word, and at a desk only Add keeps its
glyph, a `+` before the word; the top bar keeps the mark, the language (its flag alone), the
bell and the account, with find as a row in the account's sheet; the pill
that opens the conversation is a round button above the bar, and every panel comes up
as a sheet from the foot — the bell's, the language's, the account's and the doors' menus
alike — no taller than the screen less a strip of the page, over the page dimmed. Learn on
a phone is quiet (2026-09-14, "the whole page is just way too busy"): the greeting and the
count without the date, and no sheet and no row of doors: a column of cards, one for every
text the page can offer — the one carried on with, a new instalment, the suggestion, what
was read lately, what is followed — each raised on the desk with its cover, what it is to
the reader, its title in its own face, the English, the facts and the known share, the
whole card the press to its reader, and All your targums under them (2026-09-14, below).
No reader is framed on a phone. Fields are wells: no line,
the ground mixed into the card inside, 12px corners, the primary's ring on focus. "One raised layer per
view" (§9) is a reader rule; on the desk every card is raised and the sheet is the
brightest object.

**Colour.** The warm family stays. The primary is teal, `#1f6f6b` on light (5.6:1 on
paper, 5.8:1 as paper text on it) and `#6fb8b3` on ink (7.4:1): links, Send, the
active tab, the selected row, a field's focus, and the "on" state. Calls to action stay
ink-filled with paper text (§9). The brown accent keeps the reader; on the desk it is not
used. The functional hues — leaf, clay, iris, sun — mean what §4 says and nothing else,
so a teal thing is always a control and a green thing is always progress. The wash is
teal at 9%.

**Type.** The chrome speaks in Source Sans 3, self-hosted under its licence (OFL), Latin
subset, on chrome pages only; the fallback is `"Segoe UI", system-ui, sans-serif`.
Section titles 1.25rem/700, card and panel titles 1.0625rem/600, body and controls
0.9375rem, meta 0.875rem, labels 0.6875rem uppercase at 0.08em. The reading serif appears
on the desk only where a text's own words or title appear — the sheet, a card's Hebrew
title, a row in Your Words — and in the wordmark. Hebrew keeps its own faces and leading
and is never scaled (§5). Counts keep tabular figures.

**Layout.** The rem itself scales with the screen on chrome pages — `clamp(16px, 0.35vw +
12.5px, 22px)`: 16 on a phone, about 17 on a laptop, 21 on a television — so one layout
serves a hand and a wall; the reader sets its own type. A 62rem column, cards on a
12-column grid, 8px base, sections 48px apart
with no rule between them, cards padded 20px, controls 40px tall and 44px under a coarse
pointer (§8). Radii are the desk's own scale: 8 controls, 12 rows and fields, 16 cards, 24 sheets and
floating panels, 999 pills; the sheet's paper stays at 16 so it still reads as a page.
Buttons are three kinds and no more: **filled** in the primary, one per view — Send,
Open, a Follow that is on; **tonal**, tint with the primary's text, the ordinary press;
**ghost**, no fill, for Hide, Close and dismiss. All are pills. The bordered word-button
is retired.
The front page is the reader's own highlight (2026-09-11): the sheet across the row at
a reading height, and nothing else. The shelf that stood under it left the same day: the
texts read lately are a menu in the row of doors, Recently read — the last few, and the
way to the whole list at its foot — and a text read through carries a check in leaf in
that menu and in the subscriptions menu beside it, since green is progress (§4). The lists of words and phrases are a
page behind the account, and so are the series to follow. The conversation lives on no
page: one pill in the primary, fixed at the foot of every page, opens it as a drawer —
from the edge on a laptop, up from the foot on a phone — holding the conversation page
framed without its bar (`/chat?embed=1`), loaded when first opened and left open across
pages. What is typed there is answered there; a text it offers opens in the sheet on
Learn and on the reader's own page anywhere else; both frames are same-origin only, in
both directions. Notifications — what is building, what is ready, what landed — are a
bell in the ink bar with a count and a panel under it; nothing is fixed at the foot of
the window but the pill.

**Language.** One menu at the end of the places, on every desk page that is in a
language — Learn, Library, Your Progress, Add, the conversation, You and the lists behind
the account — says which language the page is in and lists the reader's languages under
it, headed "You're learning", each in its own name after English's (§12, 2026-09-14), with
"Your languages" last, where
the list itself is chosen (decided 2026-09-13; it replaced a row of tabs under the
heading that only three pages drew). The button is the bar's own kind, its panel the
bell's. Drawn only when the reader learns more than one language. The choice is kept on
the account, so another device opens in it; opening a text never moves it, because a
reader and its drawer follow their own text. Everything on the desk follows it — the
shelf, the counts and the level, what is suggested, what is added, and the conversation,
which is one per language — and what only Hebrew has (the tracks and scenes on Learn,
"Which Hebrew" on the Library, the followed series) hides under another language rather
than showing Hebrew. A text in two languages, Daniel's Hebrew and Aramaic, is on both
shelves, and a word is kept in the language of the row it was met in. This is not the
switch between finding and talking cut on 2026-09-06: that asked a reader to pick a mode
of one thing; this says which of their languages they are in, which a reader of two
already knows.

**Motion.** One curve, `cubic-bezier(0.2, 0.8, 0.2, 1)`: 240ms for a thing arriving,
160ms for a thing settling or leaving, a press giving to 0.98; none under
`prefers-reduced-motion` (§8).

**What stays the reader's.** The page tone, the serif, the hairlines between lines, the
brown, the glyphs in §7, the per-line controls, and the rule that a reader fetches
nothing — the drawer in a served reader (2026-09-11) has no address until it is opened. The reader's own chrome — its bar, the word card, the keys, its sheets on a
phone — takes the desk's corners, tiers and glass since 2026-09-11 (phase 5); the
page's lines keep §8 as written.

