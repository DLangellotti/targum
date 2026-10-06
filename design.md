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

**A text that carries media opens as its media.** The bar says it can be heard — ▶ Listen,
first among its tools — and the strip comes up when it is pressed (§12, 2026-10-05); a
picture is on. Nothing plays until pressed — inside a playlist a swipe is a press, see
§12 (2026-09-23) — and the text is still the page. This replaced
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

Focus ring `#b8935e`, inside the product. On the public pages (the front door, /connect, the
weekly, the parasha and the dailies), which stand on the desk's ground, the ring is teal
`#1f6f6b`: the gold measures 2.31:1 on `#ece7de`, under WCAG 1.4.11's 3:1, and teal is
4.8:1 there and is already a focused field's ring (§13). See §12, 2026-10-02. The mark's translation column on paper is its own value, `#a5824f` —
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
  paper text. Focus is a 2px `#b8935e` ring. In the reader a hovered line wears the same
  raised band as the line being said — except while a voice is going, when the band is
  the voice's alone and a hovered line takes a 1px rule outline instead, so the pointer
  never reads as the voice having jumped (targum-internal#420).
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

  **A line of text that answers a tap is not a control — 2026-09-22.** The rule is about
  the chrome: keys, toggles, handles, the things drawn to be pressed. A passage that
  reveals its translation when you tap it is text with a gesture on it, and the thing
  being tapped is the sentence itself, at whatever height the sentence is. Giving it the
  44px reach would put a floor under every line of a conversation and space out the
  reading to satisfy a rule written for buttons.

  So `.chat-pair` stays out of the registry, deliberately (targum-internal#241, David's
  call). What it must keep instead is the *keyboard* path, because that is the access the
  44px was standing in for: the pair is focusable and Enter toggles it, and the toggle at
  the head of the thread reveals every pair at once for anyone who would rather not aim
  at a line at all.

  The test for whether something is a control: **would it still be there with nothing to
  read?** A play key would. A line of Hebrew would not.

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


### The connector finds with one tool — 2026-10-06

Over the connector, Claude and ChatGPT were handed three tools for finding something
to read: `search_library`, `search_my_shelf` and `suggest_next`. A host had to choose
between them before it knew what the reader meant, and it often chose wrong first:
the library searched for a text already on the shelf, the shelf searched for one still
in the library. All three descriptions were also read on every turn. David replaced them
with one tool on 2026-10-06, `find_text`, titled "Find something to read".

- **One question, one tool.** With words to look for, it returns the reader's own texts
  first, then the library's, and a library text already on the shelf appears once, as
  the shelf's row. With no words, it returns what `suggest_next` returns, ranked for the
  reader, or the reader's own texts newest opened first when it is asked for theirs.
  Each row says where it came from, `mine` or `library`.
- **Hosts see 15 tools, not 17.** Fewer tools means fewer wrong first calls and a shorter
  list read every turn. `find_text` reuses the three functions and copies none of their
  logic, so a row reads exactly as it did.
- **The scope still decides.** A connection that was not granted the record sees no
  text of the reader's. There `find_text` searches the library alone and ranks it the
  library's way, gentlest first.
- **targum's own chat keeps all three.** Its page draws each result by the tool's name,
  and its prompt names them, so it is not offered `find_text`.
- **The old names still answer.** A conversation that listed the tools before the change
  can still call the three by name, under the same scopes. They are no longer listed.
- **A name searched for is not held to the reader's ceiling.** When the reader names a
  text, they want that text, even if it is harder than what they would be offered.

### A card in someone else's chat — 2026-10-06

Over the connector, everything targum says arrives as text the host's model reads and
then rewrites. A build in progress is a model calling `check_job` again and again and
saying "still working". A text is a long link the model has to copy out character by
character. Claude and ChatGPT can now each draw a small page of a server's own inside
the conversation (the MCP Apps extension, which ChatGPT's Apps SDK speaks too): the server
names a `ui://` resource on a tool, the host draws it in a sandboxed frame, and the frame
talks to the host and to nobody else. David asked for build progress to be shown this way
on 2026-10-06.

- **Two cards, and a third needs an entry here first.** *A text*: its title in the
  reading face, Hebrew `dir="rtl"`, how long it is, how much of it the reader knows, and
  one door that opens it on targum. *A build*: what stage it is at, how many chapters are
  ready of how many, the time left where it can honestly be estimated, and the door once
  the text is ready.
- **A card is chrome, not a reader.** It is drawn as the desk is (§13): the chrome's sans,
  named and never fetched; ink and teal; the radii and the type scale `test_brand.py`
  already holds. No emoji, no exclamation marks, no streaks, no confetti when a build
  finishes. Motion only under `prefers-reduced-motion: no-preference`.
- **It fetches nothing.** The page, its style and its script are inline in the resource
  the server hands over. No font, image, stylesheet or script from the network, ours
  included, which is the readers' rule applied to a frame we do not own, as it was to mail
  (2026-09-27). Whatever the card shows comes in from the tool result. A build card stays
  current by asking the host to call `check_job` again, which is free and read only.
- **A card never presses.** It can open a page of ours and it can ask for a read-only
  tool. It cannot start a build, confirm a quote or call `record_turn`: the press stays on
  targum's own page, and the scope stays the one press that lasts ("A scope is a press that
  lasts"). A card that could spend would be the model's hand with a button drawn on it.
- **The model is told less, not more.** The model gets one line it can say; the card
  gets the rows. A text card means the model writes no link, which is faster and cannot
  garble one.
- **Text is still the floor.** A host that draws no cards, or a reader who switched them
  off, gets exactly what the tool returns today: the same line and the same link.

**Two exceptions, both David's, 2026-10-06:**

- **A card takes the host's theme.** "There is one look, and it is light" (2026-09-19)
  holds everywhere targum draws its own page. A card is drawn inside somebody else's,
  and a light card in a dark ChatGPT is a bright rectangle in a dark room. So a card
  follows the theme the host hands it, light or dark, in a dark reading of the same
  palette that `test_brand.py` holds. Nowhere else changes.
- **A text card can play audio the text already has.** Hearing a line without leaving
  the chat is the most delightful thing a card can do. The play button is there only
  where a recording already exists (a scene, Be'eri, PocketTorah, a voice the reader
  already paid for), it streams from targum.page, and it never spends: a text with no
  voice has no button, and giving it one is still a press on targum's own page. This is
  the one fetch a card makes, and it is audio from our own origin, never a script,
  style, font or image.

**The dark reading** (built with the build card, 2026-10-06). It invents no colour: each
light token is swapped for the value §4 already gives it on ink, and nothing else on the
card changes. `card.css` holds both columns and `test_brand.py` pins them value by value.

| token | light | dark |
|---|---|---|
| card | `#fffdf9` | `#201e1b` |
| ink | `#1c1a17` | `#e6e1d8` |
| muted | `#6b645c` | `#9a9288` |
| edge | ink at 8% | `#322e29` |
| teal, the door | `#1f6f6b` | `#6fb8b3` |
| text on teal | `#fffdf9` | `#0f1a19` |
| leaf, the bar | `#5a7340` | `#a8c37e` |
| track | `#ece7de` | `#322e29` |

The frame's own ground is transparent in both, so the host's page shows round the card.
The build card follows a build by asking for `check_job` with `wait_seconds` until it is
done or has stopped, and gives up after an hour or three failed asks, saying so. Where a
host draws several cards for one build, the newest follows and the others show what it
hears.

**The text card** (built 2026-10-06) is drawn beside `find_text` and `open_library_text`,
one card a text and a short stack of them for a list, as many as the tool returned. Each
says its title in the reading face, the English title where there is one, its length in
minutes (a shelf text's words at the library's 130 a minute), how much of it the reader
knows in the app's own sentence ("You know about 7 words in 10 here", from the same
catalogue keys), and one door: Open, to the short link, or Open in the library for a
library text not yet on the shelf, which goes to our library page where it is got ready.
It asks for no tool at all. Both cards speak to their host through one shared bridge.

Its play button is Listen, in outline beside the filled door, and is there only when the
text already has a recording on the disk: the manifest beside an import or a voice the
reader paid for on Hear, a scene's own voicing, or the recording attached to the text's
source (Be'eri, PocketTorah, LibriVox), credited as "Read by" where the licence names a
reader. **The card cannot use the reader's session.** It plays from a host's frame on
another origin, and the cookie is `SameSite=Lax` and third-party there. So the tool
result carries, beside the rows and never in what the model reads, an address of the
form `/heard?t=<token>`. The token is a random key the server keeps against that one file
for twenty minutes, in memory. It names no path, opens nothing else, and is forgotten on a
restart. Past its time the button goes. The card's frame names targum.page in
`resourceDomains`, the extension's field that reaches `media-src`, and nothing else.
While a token lives, anyone holding the address can play that one recording without
signing in. That is the price of a card that plays, and twenty minutes is how it is kept
small.

### The connector is handed a sample of the known words — 2026-10-06

`how_to_talk` handed a host the reader's whole known list, 1,483 words on David's
ledger, beside 774 common words it overlapped with: about 22,000 characters the host
read before its first line and carried on every turn after. Over the connector it now
hands the commonest 300 known words by frequency, leaving out laughter and stretched
spellings and anything already in the common list, and says so ("the commonest 300 of
the 1,483 they have marked known"). The count is still the reader's real total.

targum's own chat keeps the whole list. It holds the prompt itself and can cache it, so
the size costs it far less. "One contract, both surfaces" (2026-09-23) still holds for
the rules. The two surfaces differ only in how many of the reader's words they are
shown (David, 2026-10-06).

### A verse taller than the page is cut between its lines — 2026-10-05

Rashi stays on by default and at full length (David, after the QA pass before the
portion's post). A verse with Rashi beside it runs to thirty lines on a phone, and a page
was a run of whole verses, so that verse had a page of its own that ran on under the
arrows, the page count, the words tab and the player.

- **A page never has a line under what stands at the foot.** A verse taller than the
  room is cut across pages between two of its lines, never through one: the verse and its
  translation are on the first piece, and the commentary carries on over the next. The
  foot of the text takes a page of its own when the last page has no room for it. On
  paper nothing is cut.
- **The voice follows the verse, not the block.** While a recording plays, the reader is
  turned to the page the verse being said is on, and its Hebrew line is brought to the
  top third of the room. The commentary under it is the reader's to page through.
- **A press that waits says so.** Download PDF is set on the box and takes seconds; the
  press reads "Preparing PDF…" in muted ink until the file is in hand. No spinner.

### A video stands beside its transcript, or large — 2026-10-05

A video text was a picture in a corner of the reading page — picked up, moved and sized
by hand — with the strip floating under it as its transport and a black full-screen mode
of its own. David chose three changes from mockups on the Kan driving-licence clip
(targum-internal#422, part of #409), building on the one-row bar above:

- **A · Beside.** The picture at the left, no chrome on it. One thin row under it: play
  and pause, the time, a hairline of where the voice is with a faint leaf band for the
  line being said, the length, the speed ("1× ▾", the six speeds as one of the bar's
  panels, under its press) and Loop this line. Under that what it is and whose: the
  title, the English title, the credit, the licence, the part and "Watch on YouTube". The
  transcript beside it follows the voice, the line being said lit with the band a chanted
  verse has, English under each line, words tappable with the reader's levels; the word
  being said is §8's selection chip where the recording was aligned word by word. The
  picture holds the left whichever way the text reads, as in the mockups — a Hebrew
  transcript's lines then begin at the window's right edge — so this one layout names the
  side per direction rather than by the reading direction.
- **B · Theatre.** The picture large, and under its row the line being said set large:
  it is the transcript's own line, copied in as the clock reaches it, so its words are
  tappable, carry their levels and light as they are said; the English small under it,
  the lines either side faded. It is a line of the transcript, not a caption over a
  film, so between two sentences it holds the one just said (the full-screen subtitle
  went dark between lines; that mode is gone). A long line is set smaller rather than run
  off the window. Transcript opens the transcript as a panel at the right and the
  picture grows smaller for it.
- **The switch.** "Beside | Theatre" in the bar, kept per reader (`targum:film-view`),
  like the speed, and `v` turns between them. Listen is not in the bar while the picture
  is up: the row under it plays it.
- **C · It steps back.** While it plays the bar and the row fade, and what is left is
  the picture, the hairline (the picture's width now) and the line being said. A pause,
  the pointer, a touch or a key brings them back; nothing steps back while a panel or a
  word's card is out, or while the keyboard is in the row. A word tapped while it plays
  stops it, so its card opens over the paused frame, which steps down under it, and the
  word stays marked in the line. `prefers-reduced-motion` keeps the change, not the fade.
- **On a phone**, one way of standing: the picture the window's width (an upright one
  held to under half the window, in the middle), its row, and the transcript under them,
  the picture staying at the top under the bar as the transcript scrolls. No switch.
- **Keys.** Space plays and pauses as on every text; ↑ ↓ the line before and after, and
  in Theatre with the transcript put away ← → as well; Escape shuts a panel or a card and
  brings the row back. The speed panel takes focus from the keyboard and gives it back.

What stays: the picture is put away and brought back from ⋯, still kept per text
(`targum:video-shut:`), and put away the page is the audio reader — Listen, the strip
once pressed, and the strip's toggle to bring the picture back. ⋯ carries Hear first, the
step either side and the file while the picture is up, because the strip that carried
them is not on the page. Full screen is the browser's, under ⋯, as on every text. The
picture comes from the reader's own folder and nothing is fetched. Inside a playlist a
video opens in Theatre, writing nothing; its end opens the transcript, where the end is.

What it overturns: "The picture can be picked up" (2026-09-13), "The picture's keys say
what they do" (2026-09-14) and the docked half of "A video text opens as its transcript"
(2026-09-17) — there is no corner, grip, size key or full-screen frame any more, and the
stores of the corner, the place, the size and full screen are no longer read. The
picture also left the phone's band: it stands at the top and is never put away by a
word's card. The 44px list in `test_brand.py` names the new presses.

### The reader's bar is one row — 2026-10-05

The bar had grown to about fifteen controls on two rows of dark filled pills, and the text
began a third of the way down the window. David chose three changes from mockups on the
real Bereshit reader (targum-internal#421, part of #409), for **every text**, not only
portions:

- **A · One row.** The mark, the title, "N of M known", then at the far end **Listen**
  (with the recording choice inside it, "Chanted ▾", where an aliyah carries two),
  **Aa**, **print** and **⋯**. Text labels and thin icons, nothing filled: the live choice
  is underlined in leaf (§4, "progress, known") and a toggle is a small switch, leaf when
  on. The same row on a phone, smaller; the English title waits for a wide window and the
  count for anything wider than a phone.
- **Aa** is how the text is set and what stands beside it: the level, the translation,
  the columns beside the verse, shnayim mikra, the vowels or stress marks, the te'amim,
  "As said", text size (a small A, a line for where the size stands, a large A) and line
  spacing. Plain labelled rows; only the rows the text has.
- **Read is the only layout; shnayim mikra is a practice** (David, on the live site, the
  same day). The first build offered "Layout: Read / By verse / By aliyah", and in the
  last two the column switches stayed pressed and did nothing, with nothing saying why.
  So the practice is its own switch in Aa, where Onkelos is beside the text as before.
  On, it says what it is — "Each verse twice in Hebrew, then once in Onkelos" — and
  offers By verse and By aliyah (By chapter on a book). While it is on, the column
  switches are grey, with "Shown in Read" under their heading, and the ×/+ on the columns
  are not drawn; pressing a column's switch puts the practice down and brings the text
  back to Read with that column on.
- **Print** is a two-line choice, this aliyah or the whole portion and its haftarah, and
  is drawn only where a server can set the paper (a portion's reader; "The week's sheet
  is a download", below). Any other text's edition is still the command line's.
- **⋯** keeps the rare things, each a row named by itself: the view (beside, under, the
  text alone — the drawings, without the sliding pill), pages or one scroll, highlighting,
  the word list, the case lens, the picture and the original, full screen, talk, Keys (the
  row says the word, the press keeps the mark), Add to playlist and Hear this section.
- **B · The columns switch themselves.** Under the pointer a column's name carries a
  quiet ×; a column turned off leaves a faint "+ Rashi · English" at the head of the first
  verse while another column stands. Both press Aa's own switch, so there is one idea of
  what is on. A phone has no hover and draws no ×: Aa is the way in there.
- **C · The bar steps back.** While a reader scrolls on or listens it fades to the mark,
  the count and pause with a thin line of where the voice is; it comes back for the
  pointer near the top, a scroll up, a pause, Escape, or keyboard focus in it, and never
  steps back while one of its panels is out. Its ground is **paper, not glass** — solid,
  so no text shows through — and its height never changes, so nothing on the page moves.
  The fade is 400ms and honours `prefers-reduced-motion`.
- **Panels are visits.** Each opens under its press on a wide window and as a sheet from
  the foot on a phone, over the page and laying nothing out (the 2026-09-14 rule for ⋯,
  below). One at a time; `aria-expanded` on the press; focus goes in when opened from the
  keyboard and back to the press on Escape; a press outside shuts it.

- **The strip waits for Listen** (David, reviewing the first build of this, same day). It
  stood at the foot the moment a recorded text opened (2026-09-03, below), which with ▶
  Listen in the bar said "you can hear this" twice. Now nothing stands at the foot when a
  text opens. Pressing Listen — or Space, or a line's own press — starts the voice and
  brings up a slim strip in the bar's style: paper, a hairline, a pill, the play press in
  ink. It carries the line of where the voice is, the step back and on, the speed, Hear
  first where it applies, the picture where there is one, the file, and ×. Its × puts it
  away and hands focus back to Listen; nothing is remembered, so the next text opens the
  same way. On a phone the file and the credit are in ⋯, as they were. A text with video
  kept its strip standing for a day, as the picture's transport; since the video viewer
  below (#422) the row under the picture is its transport, and the strip is what a video
  text has once its picture is put away — waiting for Listen like any other.

What it does not overturn: the strip is still the transport, with every control it had;
the keyboard's letters are unchanged; §8's 44px reach holds for every new press, and
`test_brand.py` lists them.

### The focus ring on the public pages is teal — 2026-10-02

A design review measured the gold ring at 2.31:1 on the desk's ground and 2.80:1 on its
cards; WCAG 1.4.11 asks 3:1 of a focus indicator. The public pages stand on that ground
everywhere. There the ring draws in teal, 4.8:1, the colour a focused field already
rings in (§13), so those pages now have one focus colour rather than two. `--focus`
itself is unchanged: the reader stands on paper, where the gold is the product's own,
and `test_brand.py` still holds the token to it.

### The front door keeps its look and moves its promise up — 2026-10-02

A tester called the front page "kinda directionless … what are the killer features
exactly? Found my answer near the bottom", and the answer he found was section 8 of 10:
*If it's in Hebrew, you can learn from it here.* A rebuild around that one promise was
tried on 2026-10-01 and set aside the same day: it lost what the page already did well —
a hero that says what targum is, and the reader under it proving it. So the page stays,
and is sharpened (targum-internal#399):

- **The hero is today's headline and lede, with one call to action**: the box, and under
  it the live page's own four points (start at any level, upload any text or media,
  hundreds of free texts and videos, no credit card required); written anew they read
  as generated (David, 2026-10-02).
  The whole word card stands beside the headline; the reader runs the full width under
  both and, leaving the top, makes room for the card in one 400ms move, keeping its
  height so nothing under it rises, and the card stays beside it while the lines are read.
- **The demos move once you reach them, and only then** (§8's "rare and purposeful" is
  kept by being the demonstration rather than decoration): the film plays itself when it
  is mostly in view below the top, each word lit as it is said and the card turning to
  one word a line; the chat's turns arrive one after another the first time the phone is
  seen, the correction's double line drawn a beat later; the vowels settle onto the
  letters one by one in reading order. The first press or key inside the reader hands the
  film to the reader for good. With reduced motion none of it moves, and without the
  script it is all simply there.
- **"Your own Hebrew" is the first part after the reader**, where it was the eighth. The
  live box stays under the headline (targum-internal#399, the entry below); this part
  shows what it gives back once you're in, drawn (the sentence about the link, how much
  you already know, when it's ready), and under it the places it reads, on ink: a photo
  of a page (a letter, a form, a sign) among them.
- **Seven stops, each answering one question**: what is it, show me, does it work on my
  Hebrew, how does it help me learn, can I practise, what is already here, how do I get
  in; the questions come before the waitlist, so the page ends on it. "Watch and listen",
  "Every word", the vowels, "Your progress" and the Torah's own part were folded into
  those or cut, because each said again what another said, and the closing form asked
  again straight under the waitlist. About a quarter shorter.
- **What is underneath is said where it is used**, in plain words and without numbers,
  model names or where texts come from: words reduced to dictionary form, root and
  binyan from scholars' analysis for the Bible and a language model elsewhere; vowels
  added and every guess marked; one word list for biblical and modern Hebrew; recordings
  timed to the voice; the portion chanted, each word lit as it is sung.
- **"Talk to targum" shows its chat on a phone, drawn as /chat draws it** (§9): turns at
  opposite edges in one ink, the correction in small capitals, why folded under a
  hairline, no bubbles. Claude and ChatGPT are one line beside it.
- **Every colour the page draws is a named token** in its `:root`, and `test_landing.py`
  keeps literals out of the rules; spacing takes eight steps (`--space-1` to `--space-8`);
  the page breaks at 30, 40 and 56rem only.
- **No claim about the order people are let in** (the batch takes the oldest, but David
  also lets people in by hand, 2026-09-28), and no promise that the waitlist hears the
  price first, which is not decided.

### The week's sheet is the edition, twice — 2026-09-28

`targum export mikra` prints the week's shnayim mikra sheet (targum-internal#105): the
portion with Onkelos beside each verse, the haftarah with the reader's language beside it,
and with `--for` the words the reader looked up that week. Everything under "A text can
be printed" below holds; this says only what the sheet adds.

- **Two readings, one page.** The portion leads under the page's title; the haftarah
  follows under a title of its own, on the same run of paper rather than a fresh sheet,
  for the reason chapters run on. The portion is set beside Onkelos because that is the
  practice — twice the text, once the targum — and the haftarah beside the reader's
  language because it is read once and never with a targum (targum-internal#203). Where
  the shelf has no Onkelos, the reader's language stands beside the portion and the
  command says so; paper does not.
- **One list, at the end, and it is the reader's.** No list after an aliyah: a portion's
  hard words would be pages of them. The one list is the words looked up that week, once
  each, leaving out any since marked known or ignored — read off the record of use, whose
  look-ups name their word since this day (David, 2026-09-28). Where the record names none
  — off on the box, stopped by the reader, or a week before it did — the list is the words
  kept that week instead, and **its heading says which**: "Words you looked up this week"
  or "Words you kept this week". Each word carries the reader's own note, or the meaning
  the page gave when it was kept, or the week's texts' first sense, and is left off where
  there is none, as the edition leaves one off.
- **The week is the portion page's week**: it begins when `pointing_at` turns, motzei
  Shabbat on the one clock, so the sheet and the page agree on which week a word belongs to.
- **A look-up names its word, and nothing else does.** The dictionary form, under the
  language of the row it was met in, so an Onkelos word is Aramaic. The privacy notice
  (clause 3.6) and the account page's plain account both say so, and the record is still
  behind `TARGUM_EVENTS` and the reader's own switch.
### A link tried on the front page is built when they are let in, on targum — 2026-10-01

The front page's box (targum-internal#399) lets a stranger paste a link and see what it is.
Joining keeps the link with their place. David chose on 2026-10-01 that **letting them in
builds it, and targum pays**: "let-in builds the saved link". It is waiting for them the
first time they sign in, and the box's copy says so ("When your turn comes, it'll be
waiting for you, ready to learn from.").

This is the one build nobody presses for, so what keeps it inside the rules is written
down. The operator's press, Let in or Open the door, is the consent, and only for a link
the person chose and joined with. The build still goes through `Library.press` and so
`Library.claim`, is a `job` row like any other, and is owned by the new account. It is a
`gift`: it passes the account's money and hours rails and records no hours against their
eight, because targum is paying, and it is held to the box ceiling like everything else.
`gift` is a field on the job, never read from a request. A describe or a build that
fails leaves the link saved, and the invitation has already gone by then. `targum
open-the-door` on the command line has no worker to build with, so it says which saved
links it left unbuilt.

### /about says what was built, day by day — 2026-09-29

"I want /about to show that we're building in public, and display day by day what's been
built or improved, without getting too technical, without saying what doesn't need to be
said out loud," David wrote, and chose the rest. The heading is **targum is built in
public**. The calendar stays, and under it each day has one to three lines, newest first,
from the first day. The page draws the newest ninety.

- **It is written for peers and partners**, and it is plain outcomes: what changed for
  somebody using targum, and nothing about how. This is §6's "the specific line", without
  the selling; the page asks for nothing.
- **Two subjects are not said: the back office, and where a text comes from.** Work that
  is built and not switched on is said like anything else.
- **Nobody reads a day's lines before they are shown**, as nobody reads the weekly. The
  guard is `about.refused()`, asked by a test and again by the page, so a refused line
  that reached the file is still not drawn. A word comes off its list when David takes
  it off.
- **The lines are English on every page.** The Russian page says its own heading and
  dates, and marks the list `lang="en"`.
- The list is ink and ink-soft on the card, with a rule between days. Leaf stays the
  calendar's (§4), and the date stands over its lines on a phone.

`deploy/built.md` is the brief.

### The copy audit's answers — 2026-09-28

The English copy was audited end to end (`COPY_AUDIT.md`). Its open questions went to
David, and he answered them (`COPY_QUESTIONS.md`). Five of the answers undo names or
silences recorded in earlier entries below. They are listed here so nobody restores the
old wording.

- **"Save as a text", not "Save as targum"** (2026-09-06). A newcomer doesn't know that
  "a targum" is our word for a bilingual text, and without the article the label read
  like a file-dialog item.
- **The sign-in page is headed "Sign in to targum"** (2026-08-24 cut its copy). The
  tagline headed a page people reach by pressing Sign in, and the only "Sign in" on it
  was a link back to itself. The sign-in email already used this heading.
- **The ladders say what they are** (2026-08-24: "the limit is all that is said"). A
  newcomer meets "ב+" or "A2" with nothing to say which end is the start. Hebrew: "Ulpan
  classes in Israel run from aleph, for beginners, to vav." Other languages: "The
  European scale runs from A1, for beginners, to C2." The limit, "A guide, not a
  placement", still follows each.
- **No "free" inside the product.** This applies §6 ("inside the product there is no
  price") to two places that had drifted: the refusals that ended "The library is always
  free" now say "The library still opens", and the From targum playlists (#415) now say
  "Opening them uses no credits".
- **Followed series are "Following", not "Your subscriptions"**, so the word stays free
  for a paid plan. /you is "Your profile" everywhere.

What does **not** change: the approval page still says "Chatting is included" and names
no allowance (2026-09-24). Only the public /connect FAQ says what chatting is included
in: "your monthly credits". That is true, since a turn is metered into the monthly pool
(2026-09-23), which is also why "Chatting uses no credits" was rejected.


### The copy audit's answers, where they were behaviour — 2026-09-28

The entry above is the wording. These are the answers that needed code (`COPY_QUESTIONS.md`
§B, §C and §E), each because a page said something the code did not do.

- **A signed-in reader is not asked to join.** This amends "The weekly, the parasha and
  the dailies are drawn as the front door is" (2026-09-27, below), which ends each page on
  the waitlist. §6 says somebody who has chosen targum is not sold to again, so for a
  reader with a session the bar's Join the waitlist, the hero's form and the closing
  section are not drawn, and the Read button leads the hero, ink-filled. A stranger sees
  the page as it was.
- **A spending press has its cost beside it.** The press page, the set page and Telegram
  already said "Uses N credits"; now the Add page's card, the chat's card, a waiting
  chapter's Translate or Transcribe, the contents page's per-chapter press and Prepare
  all say it too. A recording or a film in credits — a minute each, any part of one a
  whole one, as `credits_of` counts — and a text "Uses none of your credits". Only where
  the figure is known where it is drawn: a recording whose length the page does not
  carry says nothing rather than a guess. And the description search on Add says no cost
  at all: it is a turn of chat, and chatting is included (2026-09-24).
- **The verbs follow the medium in two more places** (§6). The contents page's first
  press is Start listening or Start watching for a recording or a film, and the ready
  email's button is Read, Listen or Watch, chosen as its subject is. A scanned PDF offers
  "Read the 12 pages" and a post whose words are all in its pictures "Read the 3
  pictures"; "Also read" stays for a post whose caption was read.
- **An archived issue of the weekly is worded around its date.** "This week's" is said
  of the newest published issue only; an older one's hero reads "as it was on {date}".
- **On a hosted box a refusal never hands a reader the machine's words.** A status code,
  a curl exception, "install yt-dlp", "set OPENAI_API_KEY": the reader is told the
  `job.unreadable.*` sentence for what happened, and the detail goes to the log. On a
  machine somebody runs themselves the reader is the operator, and keeps the detail.
- **Every door says what is true of a closing account**: "This account is being closed.
  To keep it, email hello@targum.page." And an uninvited address is pointed at the
  waitlist while the front door is open.


### The arrival opens with a welcome, and says what is optional — 2026-09-28

David, trying the arrival as a new reader on the live site: "very weird to come and see
this as first screen. No welcome, no telling you where you are, no asking your name, just
a question!" And of the connector's card: "this makes it seem like installing the MCP is
mandatory. Make it very clear that it's optional", and "the skip and open buttons do the
same thing there, don't they?" They did.

- **A welcome comes first** — after the language, where that is asked, since it decides
  what language the welcome is in. "Welcome to targum", a line on what targum is, a line
  on what happens next, and **What should we call you?**, optional, asked only where an
  account can keep it; the greeting uses it at once. It asks nothing that has to be
  answered, so its press is **Continue** and there is no Skip.
- **The bars count questions and nothing else.** The welcome is not one, and nor is the
  connector's card: counted, "3 of 3" made it a step to get through.
- **The connector's card says it is optional**, three ways: "Optional" over it, a first
  line that says targum does not need it and that it can be done later from Learn, and a
  single press, **Continue**. The Skip beside it did what Continue did, and two ways past
  a card read as a card to get past.

The waitlist's pages had one heading for every answer, "the waitlist", over "Thanks.
Check your email and press the button in it." Each answer has its own heading now —
"You're on the list" (it was "Thanks for joining" until 2026-10-02), "Confirm your place",
"You're on the list", "You're off the list" —
and sentences a person would say. Each heading follows from the step alone, so the
answers that must not say whether an address is waiting still cannot.


### Russian is shown to somebody who may read it — 2026-09-28

"I don't want a non russian to see any russian. Figure out how to design this as such,"
David wrote of the arrival's first screen, which asked every new reader "What is your
native language?" and "Какой у вас родной язык?", and offered "Other · Другой".

**This amends "The arrival asks which language first" (2026-09-20, below) in one rule:**
it said the question is asked "of everybody who has never said … not only of a browser
that says Russian", because an olah's phone is as often set to Hebrew or English. The
question is now asked only where the browser gives a sign: one of its languages is
Russian, or a language of the countries where Russian is the language people share
(Ukrainian, Belarusian, Kazakh, Kyrgyz, Uzbek, Tajik). Everybody else starts on the
subjects and sees no Cyrillic anywhere in the arrival.

The reader that entry was written for still has a way in, and it is the front door's own:
**EN · RU**, in the card's corner, beside the step. Two Latin codes, so it shows no Russian
to anybody, and a Russian reader knows it on sight. It is drawn only where the question is
not asked and nothing has been said; pressing RU is the answer the question would have
taken — kept in the browser, told to the account, the page loaded again in Russian. The
signals that were already answers stay answers: a press on the front door's switcher,
the operator's mark on an invited address, the account's own rows.

What is not touched: a language menu a reader opens lists each language in its own name
(§12, 2026-09-14), because opening it is asking; the conversation's own question was
already asked only of a browser that says Russian.

And the level question reads **"How much Hebrew do you know?"**, with "You'll start there,
and we'll adjust as you mark words." under it; the third rung is "I can hold a simple
conversation", in the first person like the rest.


### The connector is met on the way in, and in four places — 2026-09-28

"We need to make sure the user understands the existence of the MCP and how to install it
earlier," David wrote, and chose all four places offered: the arrival's last step, a line
in the reader, a fuller banner on Learn, and before sign-up. What stood was "The connector
is a banner and a line in the foot" (2026-09-24, below): a banner above Learn's row and a
line in the foot. Since the arrival became a page of its own and opens a text directly
(the entry after this), a new reader could go days without standing on Learn, and the
banner was hidden while they answered — so the one announcement came late or never.

The rule that entry kept — **it goes when it has been taken up**, which the account
already knows — holds in all four. Each is drawn only while the connector is open
(`TARGUM_CONNECTOR`) and, inside the product, only to a signed-in reader with no
connection. And the thing each one does is the same: say in a line what a reader gets,
and put the address, with Copy, where the first step of installing it is one press.

- **The arrival's last card.** After the rung, one more screen, counted in the bars: what
  the connector is, the address and Copy, and "Learn more" to `/connect` in a
  new tab. The filled press is **Open** — the text the answers chose, as before, and §6's
  neutral verb, since the card cannot know yet whether it is read, heard or watched — so
  installing is offered and never stands between a reader and their first page. Skip
  does the same. It is not a question and asks for no answer; it is the one card in the
  arrival that tells rather than asks, and it is last so that nothing about it holds up
  the three that are asked.
- **A line in the reader, at every finish.** Under the count the offer already carries
  ("You already know 14 words in this one"), and in the same row: "Practise the words you
  marked in Claude or ChatGPT", and Connect. In answer to a press and never on load, and
  nothing above it moves — the third moment's manners (the entry "Three moments in ten
  minutes", below) — but not once: at every finish while the reader has no connection
  (David, the same day: "why can't we have it always?"). It goes when it has been taken
  up, which only the server knows, so the server says whether, in the answer the finish
  already asks for, and a page on the shared shelf carries nothing about the reader. The
  count beside it is still said once. A finish is the moment a reader has words to
  practise, which is what the connector is for.
- **The banner is a card.** It said one line and Connect. It says what a reader gets,
  shows the two steps — copy the address, add it in the app — with the address and Copy
  in a well, and links to every app's steps. Still above the row, still gone once
  connected, the cross still per-browser.
- **Before sign-up, it is mentioned lightly, once on the front door**: one line in the
  part about talking to targum, "It works in Claude and ChatGPT too.", and the way to
  `/connect`. A part of its own was drawn first and David took it out the same day
  ("remove this, and simply make a mention in the AI assistant section"). The point in
  the list under the headline came out on 2026-10-02: first thing on the page, Claude and
  ChatGPT read as what targum is built on ("oh so you're just another chatgpt wrapper"),
  where further down they read as somewhere else it goes. The invitation mail says it in
  a paragraph with the way to `/connect`. All of it only while the connector is open.


### The arrival is a page of its own, and a text they can follow — 2026-09-28

"This needs to be much prettier, delightful, and more inviting," David wrote of the
arrival, and then: "the what to work on is really weird to have on the page right away. I
think the onboarding step by step should be on another initial page." And having
finished it: "it didn't bring me to a reader — it should bring me to a reader at my level
that I'll enjoy."

**It is the screen at every width.** "The arrival is two questions" (2026-09-19, below)
kept it on the desk ground above the sheet at a desk, so that "somebody who ignores it
still has a text open", and made it the screen only under 40rem. At a desk that put the
fold, the rail and a framed reader under three questions a new reader had not answered,
and the first thing they met was a list of words they had never marked. Now nothing else
is drawn while it is up — the greeting, and the questions — at every width, and the last
answer (or the last Skip) opens the text as it already did.
The pill that opens the conversation keeps its corner (§13).

**It is one card, and it is the brightest thing on the page.** There is no sheet under
it to compete with any more, so the argument for leaving it on the ground is gone: the
question stands in a card at the sheet's corner (24) and the raised tier, a column
narrower than the page, with the question at 1.5rem. Where they are is said in words and
drawn as three short bars in leaf, since how far along is progress (§4); the words stay
for anybody not looking. A screen arrives with the desk's curve (§13) and nothing moves
under `prefers-reduced-motion`.

**A picked subject is on, and on is the primary.** The chips were quiet ink when picked,
after §4's "selection is quiet ink, never accent". The accent is the reader's brown and
§13 says the desk does not use it; what §13 gives the "on" state is the primary. A picked
subject takes the primary's tint, its text and a ring of it; an unpicked one sits on the
ground's tone inside the card. It is not filled: Next is the one filled press (§13), and
the chips are answers, not actions — a first cut that filled them put four primaries on
the page, and `test_pages_browser` refused it.

**The first text is at their rung, read off the text.** The rung picked a row by its
place in the subject's list — aleph the first, vav the last — so the one row filed under
a subject was every rung's answer, and "Just starting" opened a vav article. Now the rung
is matched against the rung a row was written for (`level.name`), the hardest at or
under it; a subject whose rows are all more than a rung past it gives way to the next
subject, because a text they cannot read is not one they will enjoy; and where no subject
is left the rung chooses from the modern shelf, as it already did for a reader who named
no subject — reach first and the voice after it, since the second moment (below) is found
on a page the reader can follow. A shelf that does not say its rung keeps the old rule.

### The words to know before a chapter — 2026-09-28

A reader may carry, above a chapter's first line, the words worth learning before reading
it (targum-internal#97): the Learning Biblical Hebrew Workbook's list at the head of a
passage. **Behind `TARGUM_PREREAD`, off**, because the card's gate — readers seen building
it by hand from the export — cannot be met while there are no readers, and David chose to
build it to be looked at rather than wait (2026-09-28).

- **The printed page's words, before the text rather than after it.** The rule is the
  printed edition's (2026-09-27, below): no names or numbers, the looked-up bands, a word
  only where there is a meaning to set beside it, the first sense. Ordered by how often a
  word comes round in the chapter, with the count typed as §7's multiplier; forty shown.
- **The reader's own words come off it, in the browser.** A page on the shared shelf is
  built once for everybody, so the page carries more than it shows and the script takes
  off what this reader has marked known or put aside. Nothing is asked of the server and
  nothing is fetched. Nothing left, nothing drawn.
- **Folded, flat and above the text.** One quiet line in the UI face with a count
  in the detail face; opened, the source at the reading size in its carried face and the
  meaning muted beside it as a translation at rest is (§9). A list on the page, not a
  card over it: the page's hairline, no shadow (§8). On pages, the first page only.
- **A `<details>`, not the fold's button** (`_fold.html.j2`), because it has no controls
  in its heading to protect and it opens with no script. Its summary is in the thumb
  registry.

### How French is said is drawn over the text, never into it — 2026-09-28

A French reader gets a switch of its own, **As said**, on `n` as the vowels are on a Hebrew
page (targum-internal#266). **Behind `TARGUM_FRENCH_IPA`, off**, until a person has read the
gold set its liaisons are scored against: the set was drafted by a model, and the card's
floor, a precision of 0.98, is only as good as the gold under it.

- **What it marks.** The liaisons every speaker makes — a determiner before its noun or
  adjective, a clitic pronoun before its verb, a verb before its inverted pronoun — with
  the consonant heard; every elision; and the final consonants nobody says. **An optional
  liaison is left unmarked**: natives make about one in five of them in speech, and a
  switch that marked them would teach a rule that is not one.
- **Drawn, not written.** Every mark sits on characters the text already has: a tie
  under the space a liaison crosses, with its consonant small above it in the UI face at
  the label size; the same tie under an elision's apostrophe; the silent letters in muted
  ink. The tie and the consonant are out of the flow, so switching moves no line, and
  since nothing is inserted every offset, every kept phrase and every saved word is the
  same with the switch on or off. A page's mute e is not greyed: the switch is about
  consonants.
- **Muted ink, not the accent** (§4). The accent is for what the reader has kept; a
  liaison is a note on the text, as a translation at rest is (§9). No hue, no underline.
- **The card says the word as it is said here**, in IPA, with its liaison consonant and a
  tie where it has one (*les* before *enfants* is /lez‿/), in the card's reading line.
  A word the lexicon has no reading for shows none, as `pronounce.sayable` would have it.
- **The switch icon** is a line diagram of what it does (§7): two letters and the tie
  between them.
- **The source is named at the foot** of any page that shows a reading: Morphalou, its
  licence and the one reading targum corrects, which the licence decision asks.

### A word in scripture names its accent — 2026-09-28

David approved it on 2026-09-28, with the technical terms (targum-internal#329). The
engine underneath was already built: `vocalize/trope.py` names every accent of the prose
system and divides a verse into its phrases, and since the same day the chanted Torah
keeps a clock for every word rather than one per verse.

The page already shows every mark the Masorah wrote. What a learner cannot do is read
them: a tipcha looks like a mercha turned round, and nothing on the page says which one
ends a phrase. The card is where a word is asked about, so the card is where the mark
gets its name. The page stays as it is.

- **One line: the name of the accent that rules the word, and its class.** "tipcha ·
  disjunctive", "munach · conjunctive" — the grammar's words, not a learner's gloss on
  them. Under the pronunciation line, in the card's own quiet style: muted ink (§4) at
  the card's own size. No icon, no glyph of the mark (the word above already shows it),
  no colour for the class, and no rank: "king" and "count" are the reference page's
  words, not the card's. A class drawn in two hues would put a second colour system on a
  page that has one.
- **Russian transliterates the name and translates the class.** The catalogue had no
  Russian names for the accents to reuse, only "знаки кантилляции" for the marks as a
  whole, and the names themselves are the tradition's Hebrew and Aramaic. So a name is
  transliterated from the English line's spelling ("типха", "закеф катан", "мунах
  легармей"), and the class is said in plain Russian, «разделительный» or
  «соединительный». Each name is its own key in the catalogue, so a better-established
  Russian set, if one is settled on later, replaces them without touching the code.
- **Only while the marks are shown.** With the chanting marks taken off (the ⋯ control,
  "Scripture has a third form of its text", 2026-09-01), or the vowels off with them, the
  line goes too: it would describe something the page is not showing. A text without
  cantillation never has it, and nor does a text that is not scripture.
- **The ruling accent, and nothing that is not one.** A word carrying two names the one
  that governs it, its strongest disjunctive. Meteg shares silluq's codepoint and is not
  an accent, so it is never named. A maqaf pair is one unit and names the accent of its
  last word, which is the one it is chanted to.
- **The poetic books get no line.** Psalms, Proverbs and Job outside its prose frame are
  accented in another system, and a prose name on a psalm is wrong with a straight face.
  No line, rather than an approximation, until that system has a table of its own.
- **The line is where "hear the phrase" will go, and is not a control yet.** The phrase is
  the run of words one disjunctive closes, the conjunctives leading up to it included,
  and its sound is their clocks, first to last (`Part.phrase_spans`). Playing it on a tap,
  and lighting the phrase while it plays, is its own entry when it is built; until then
  the line is text.
### The Tanakh map is the knowledge ramp, and Aramaic is off it — 2026-09-28

`/tanakh-map` draws every chapter of the Tanakh as a square (targum-internal#144), shaded
by the share of its running words the reader has marked known. The issue asked for the
ramp's steps and the Aramaic treatment to be written here, since the mockup's four-step
leaf fill never was.

- **The ramp is the charts' own four leaf steps** (`--step-1` … `--step-4`, words.css),
  and a fifth tone under them: a chapter measured and not yet within reach is `--rule`,
  the "nothing yet" the day strip already uses. The turns are **50, 75, 90 and 95%** of
  running words (`coverage.MAP_STEPS`), packed at the top because running words climb
  fast: the commonest hundred dictionary forms are about half of any chapter, and 95% is
  where reading goes on without stopping. A share is rounded down, so a square and its
  card never disagree across a turn.
- **What is not on the Hebrew scale never wears a leaf.** Aramaic — Daniel 2–7, Ezra 4–6
  and 7 — is the charts' `--off`, named in the legend and the card as not measured yet,
  and is shaded from an Aramaic list only once there is one. A book the library does not
  have is a dashed outline with nothing in it and no link: unavailable, never 0% known.
  A square not yet shaded — signed out, or before the answer lands — is a hairline.
- **This week's portion is ink**, a ring inside the square so the shade under it still
  reads.
- **The squares are pointed at, not pressed, on a phone.** At seven pixels a square
  cannot take §8's 44px without taking its neighbours' taps, so under a coarse pointer a
  tap shows the card and the card's **Read**, tonal, is the press and is in the thumb
  registry. With a mouse the square is the link. The keyboard meets the map as one stop
  and walks it with the arrows, rather than as 929.
- **A card, not the desk.** The map stands on a card because `--rule` and the first
  step are too close to the desk's ground to be told apart on it; the chapter's card
  floats at the foot of the window, a floating panel's tier (§13).

### The back office is four tabs — 2026-09-28

"The back office has so much going on now, time to organize into menus and tabs," David
wrote, and chose the shape: **People** (the waitlist and its door, accounts, the last 30
days), **Traffic** (visitors), **Shelf** (proposed and wanted), **Operations** (services
and balances, incidents), on one page and switched in place, with no counts on the tabs.
Above them, one line says whether anything needs doing: how many wait, visitors a day,
accounts active, incidents. The open tab is named in the address, so a form's answer
lands on it; the panel's id is not the tab's name, so the browser never scrolls past the
tabs to reach it. Without the script every panel shows, as the page always did.

Each person is let in by hand (David, the same day): a **Let in** on every row that
confirmed and has not been let in, beside the batch's "Open the door", and the row says
the date once they are. The state is said as what it is, "Confirmed their email", because
`on` read as let in and nobody had been.

The Visitors headline is a rate, "about 3 visitors a day this week", because the sum of
thirty days' visitors read as that many people. What counts as a visitor is `visits.py`'s
to say: a browser's own page load, signed out, not from an address signed in the same
day, and not a crawler or a probe.

### One foot, for the site and the app — 2026-09-28

The site had two feet, the app's and the one the public pages wore, drawn by six
stylesheets into six slightly different rows of small links. David asked for the foot
to be designed once for everything, with X added, and chose each part:

- **The lockup and two columns.** The mark and the name, the landing's one-line
  description under them; at the far edge, **targum** (About, Install MCP, Source) and
  **Follow**. A thin line under them carries © and the licence, Privacy and Terms, and
  EN / RU on a public page. A **Read** column (Library, the weekly, the parasha, the
  daily cycles) stood between them for the morning and came out the same day (David):
  the foot is for targum itself, and the reading pages have their own ways in.
- **Plain names.** "What's built" is **About** and "targum in your AI" is **Install MCP**
  (David, 2026-09-28). `/connect` still explains what MCP is for somebody who has never
  added one; the foot names the action.
- **Social accounts as §7 glyphs.** X, Instagram and LinkedIn are drawn as the
  interface's own icons (16 units, a 1.4 stroke, round caps, no fill), in ink, never in
  the platforms' colours (§10), with the name as the label. X is `@targum_app`, because
  an X handle cannot hold the domain's dot.
- **The waitlist is a line**, on public pages only, while the front door is open: the
  call to action's words in ink under the description, not a second button under the
  page's own. **Sign in is under it** (David, 2026-09-28), quieter: the two doors
  together, the new reader's first.
- **It links only to pages that answer.** Install MCP while the connector is open, the
  legal pages once they are published, the waitlist while the front door is.

One file draws it (`_site_foot.html.j2`), and it carries its own stylesheet
(`foot.css`), with every token's value written beside it, so it looks the same under
the landing's sheets, the reader's and the desk's.

### "Met" means a section you finished — 2026-09-28

The word card can say where a reader has met a word ("met in Jonah 1:4, Ruth 2:1 and 6
more"), how often it comes round ("4× in this text · 241× in the Tanakh") and how many
words of a verb's root they have met ("6 words from כ־ת־ב met, 3 known"), with the root
the way in to those words (targum-internal#95, #96). It is a line that tells somebody
what they have done, so what it claims is set down here.

- **Met is inside a section the reader finished.** Not a text opened — Genesis is one
  document, and opening it is not meeting fifty chapters of words — and not a word
  marked, which has no place. A chapter read and never finished is not claimed: the
  line undercounts rather than tells a reader they did something they did not.
- **The page the reader is on is not a place they met the word.** They are meeting it now.
- **A verse is named by its reference; anything else by its title, once.** A recording's
  "part 1:2" and a page's "p1" name nothing a reader would know. Three places are named,
  latest first, and the rest are a number.
- **Nothing with nothing to say.** A count of zero, a root with no word met, a text not
  built on this box: no line, never a zero and never a guess. The root is a plain word,
  as it always was, until there is a word of it to open.
- **It is metadata, drawn as the register line is**: muted, a line each, Hebrew in its
  own `bdi`. The root, where it opens something, is drawn as the other ways on its line
  are — accent with a hairline — and is in §8's thumb registry.
- **Behind `TARGUM_OCCURRENCES`, off unless the box says so.** Both cards were gated on
  readers — Biblical readers reaching the modern shelf, the card being where readers
  linger — and that gate cannot be met with none; David had it built behind a switch
  instead (2026-09-28). Off, the card is byte for byte what it was and asks nothing.

### The weekly, the parasha and the dailies are drawn as the front door is — 2026-09-27

"Parasha and dailies and weekly digest pages should be updated to fit design of rest of
website," David wrote, "and call to action would be to join waitlist." They were the last
public pages still drawn the way the front door was drawn before #69: a masthead with a
quiet Sign in, a serif headline, an ink band with a picture on its other half, and an
inverted door at the foot asking a stranger to sign in to an account they could not yet
have.

Now they are drawn as the landing is, from the landing's own parts:

- **The bar is the landing's** (`_front_bar.html.j2`, which the landing includes too):
  glass, sticky, the lockup, the landing's places, EN / RU, Sign in, and **Join the
  waitlist** as the one ink call to action (§9).
- **The hero is the landing's**, on the desk's ground (§13): the chrome's sans at the
  landing display step (§5), the lede under it, and the waitlist's form
  (`_join_form.html.j2`) with the line that says what happens next. Reading is the second
  thing, a tonal button to the frame below — the text needs no account, keeping a word
  does, and the waitlist is the way to that.
- **The picture stays, as a card.** The scroll, the codices and the Gaza floor are still
  the rule of "a picture of a thing" (2026-09-01, below); they now stand beside the
  headline as a card raised by its shadow instead of as the other half of an ink band.
  The band's one inverted block went with it, and so did the door's. The weekly's stack of
  front pages stands on the desk bare, as it did (2026-08-31).
- **The page ends on the waitlist** (`_front_join.html.j2`), the landing's own closing
  section, where "Keep what you learn" and its Sign in stood.

Everything between the hero and the foot — the levels, the aliyot, the frame, Why targum,
Made honestly — keeps its structure and takes the chrome's face for its labels and section
titles. `front.css` carries the landing's values under `body.front`, because `reader.css`,
which these pages still load, means something else by `.bar`, `.hero` and `.label`; where
the two copies differ, `landing.css` is right.

### The week's sheet is a download — 2026-10-04

Download PDF on a portion (targum-internal#415): in the ⋯ menu of its reader, and a tonal
button beside Read on its public page. It is the sheet `targum export mikra` prints, set
on the box when pressed. Everything under "The week's sheet is the edition, twice" holds.

- **Signed in, the list is the reader's**: the words they looked up this week, or kept,
  as the command gives them. Signed out, the sheet has no list and is in the language the
  page answers in.
- **The plain sheet is kept and a reader's is not.** The one with nobody's words on it is
  the same for everyone in that language on that paper, so the box keeps it; a reader's
  is set each time and kept nowhere, because a file of their week on the box would be a
  second copy of their record.
- **This week's portion takes this week's haftarah and date**, as the page does; any other
  portion takes its own haftarah and no date.
- **Onkelos where the shelf has it**, the reader's language beside the portion where it
  does not, and the paper does not say which.
- **A sheet that cannot be set is one sentence**, "The PDF can't be made right now. Try
  again in a minute.", whatever the reason — no Pango, a corpus built before the sheet, a
  press that ran past its time. The reason is in the log.
- **The paper is the page the reader was on** (David, 2026-10-04). The link carries the
  view: the companions on and in their order (a translation by its language, Onkelos as
  `targum`, Rashi as `rashi` once the shelf carries him), the vowels and the te'amim, beside
  or under, the marks on or off, and this aliyah or the whole portion with its haftarah.
  Each default is the reader's. `/parasha` has no reader behind it, so it asks the few
  choices that change the paper in a row of boxes beside its button, ticked as the reader
  opens.
- **It is ours, quietly.** The lockup once, small and centred over the first title with a
  hairline under it, the way a publisher's name stands on a chumash's title page; the mark
  at §2's 4 mm and `targum.page/parasha/<slug>` at the foot of every page, in the page
  number's ink; §4's paper behind it all. The wordmark is set in the page's reading face
  rather than taken from `lockup.svg`, whose live text names a face the box may not have.
- **The words being learned are lit as the reader lights them**, leaf at the step's wash
  with the hairline under it, and their meaning stands just above the word, small, in
  the chrome face and muted ink, the first time the word comes in an aliyah. Known words
  are plain. Signed out there is nobody's list, so the words in the looked-up bands get
  their meaning above them and nothing is lit. A meaning is the reader's own, else the
  text's glossary, cut to a first sense that fits; where there is none the word is lit
  and nothing is set above it — paper never buys a meaning. Above the word rather than
  in ruby: the typesetter does not lay ruby out, so the word and its meaning are one box
  whose baseline is the word's, and the lines are set a little further apart to hold it.
  The box is as wide as the wider of the two, so a long meaning moves the next word
  along rather than printing over the next meaning; and with meanings on, every line of
  the text is one height that already holds one, so the column keeps one rhythm whether
  a line carries a meaning or not (2026-10-05). Without them, the reader's leading.

### A text can be printed, and the page is the reader's — 2026-09-27

`targum export pdf <folder>` sets a reader's edition on paper (targum-internal#105). The
readers who most want the weekly portion cannot use a screen on Shabbat, and paper is the
one form of the product that does not ask them to. Nothing in this file spoke of print
beyond the mark's minimum size, so what paper takes from the rules above is written here.

- **The page is the reader's, not a new design.** §5's faces, sizes and leading, §4's
  paper and ink, the parallel mode's two columns and 2.5rem gutter, the verse number in
  the margin in the detail face. Under rather than beside is the interlinear mode's rule.
  The values live in `assets/print.css`, which `test_brand.py` reads like every other
  stylesheet.
- **The Hebrew face is carried, as the reader carries it, and chosen by the same rule:**
  what the text holds, not the shelf and not the switches. Scripture prints with its
  te'amim, because the reader shows them until they are turned off; `--no-accents` and
  `--no-vowels` are the reader's two switches, set once.
- **Paper keeps nothing the reader presses.** No bar, no card, no player, no colour for a
  kept word — a hue on paper is a hue with nothing to answer it. The one thing added is
  what a card would have said: after each chapter, its words and their first sense, each
  word once, where it first appears. The words a reader has not marked known where the
  command is told whose edition it is (`--for`), and the looked-up bands where it is not.
  A word with no meaning yet is left off, because paper cannot offer to look one up.
- **Chapters run on.** A reader turns a chapter at a time; a printer should not spend a
  sheet on a title and a byline.
- **The week's sheet has a button; the edition does not yet.** A control belongs in the ⋯
  menu and asks for a server that can set the page. The portion's reader has one since
  2026-10-04 (below); any other text's edition is still the command line's.

### Mail is drawn, and fetches nothing — 2026-09-27

Every mail a reader can receive was plain text until today, on the argument in `mail.py`
that "it is a link and a sentence; anything more is a thing to maintain and a reason to
land in a spam folder". That held while the sign-in link was the only mail. There are
seven now: the sign-in link, two confirmations (the waitlist and the Weekly News
Digest), the invitation off the waitlist, the digest itself, a followed series'
instalment, and a build that finished while the reader was away. Several of them go to
strangers who have never seen the product. David asked for them to be designed, and
chose HTML for all seven.

- **Every mail is HTML with a plain-text alternative**, sent as multipart/alternative.
  Both halves are drawn from one list of blocks in `letters.py`, so they cannot say
  different things. A link in the text half is on a line of its own, and both halves go
  as base64 wherever they are not plain ASCII, so no encoder breaks the token.
- **The frame is the desk (§13).** The ground is the desk, the mail is one card of at
  most 600px on it, the text is ink in the chrome's sans (named, never fetched: the
  fallback stack is what a mail client shows), links are teal, and the one call to
  action is an ink-filled pill (§9). A text's own title is in the reading serif, and
  Hebrew is `dir="rtl"`. In plain text, English leads and a Hebrew title sits in an
  isolate (see "The Hebrew-first audit" below).
- **The logo is in the mail, drawn and not loaded.** The mark's two columns are table
  cells with a background colour, the translation column 3px lower, in the mark's own
  paper values (`#201e1b`, `#a5824f`). The wordmark beside them is live text in the
  reading face at 600, lowercase. Gmail and Outlook strip inline SVG. A CID-attached
  image would fetch nothing, but many clients show it as an attachment, so it is left out.
- **It fetches nothing.** There are no images, no remote stylesheets or fonts, no
  tracking pixel and no redirecting links. That is the readers' rule (§13, "What stays
  the reader's") applied to mail. The provider's open and click tracking stays off,
  because one adds a pixel and the other rewrites every link. `test_mail.py` pins it.
- **Light only.** The mail declares `color-scheme: light only`, because there is one look
  (see "There is one look, and it is light" below). A client that inverts anyway gets a
  palette that survives it: nothing is an image of text.
- **The digest and the series are lists, and say so.** They carry `List-Unsubscribe`,
  RFC 8058's one-click `List-Unsubscribe-Post` and a `List-Id`, a stop link in the foot,
  and a slot for a postal address that stays empty until one is configured. The other
  five are transactional or asked for once, and carry none of these.
- **Daily series are not mailed.** A daily cycle's instalment lands on Learn and in the
  bell, but a mail every day is the ping a reader deletes an app over (Dmitry,
  2026-09-16). Weekly or slower is mailed.
- **The digest has one public name, Weekly News Digest** («Недельный обзор новостей»),
  in its subjects, pages and strings. "the weekly" is the team's word, which §6 names as
  the public-page failure mode. מבט השבוע stays as the issue's own Hebrew masthead.
- **A long build still mails its owner unasked.** After three minutes it mails, in the
  reader's language, and says why: "your text took more than a few minutes to build".
  David kept it.

### An editor settles a reader's proposal — 2026-09-27

A reader's correction is a proposal until somebody with standing settles it
(targum-internal#164: "not a vote"). Until now that somebody was the author. A paid
editor is the second hand with standing, and their verdict closes a proposal just as the
author's does. David, 2026-09-27, targum-internal#354.

- **The flow.** `targum corrections --proposed` lists the queue; `targum settle ID
  --accept|--reject --by editor --editor NAME` settles one. Accepting applies the meaning
  and refusing changes nothing, whoever presses. Either way the proposal leaves the
  queue and cannot be settled a second time.
- **How an editor is counted.** The decision is a row of its own, `who = "editor"`,
  `licence = "targum"`, under the editor's pseudonym (`Store.editor_judge`: their name,
  folded and salted the way a reader's account is). So a proposal an editor accepted is a
  reader and an editor agreeing, two judges in `Store.agreed`; two named editors are two
  judges; one editor twice is one. An editor left unnamed is counted by role, so every
  unnamed editor is one judge. A refusal never reaches the gold set, whoever made it.
- **The default stays the author.** `--by` defaults to `author`, so a settle with no hand
  named is the author's, as it always was.

What it does not change: a reader still cannot settle, and a model is never a judge.


### A haser word counts as the male word the reader knows — 2026-09-27

The press card's "You know about 6 words in 10 here", and the number the chat ranks
articles and feed items by, come from `level.known_share`: the text's tokens, bare of
points, against the reader's known forms and the commonest words. Taking the points off
a pointed page leaves ktiv haser (ארועים), while the common words and most of what a
reader marks are ktiv male (אירועים), so a reader who pasted a vocalized page was told
they knew less of it than they do. David, 2026-09-27, targum-internal#349.

- **The tight rule.** A token counts as known when putting back an inner vav or yod —
  only those two letters, only insertions, never at the first or last letter — gives a
  known form, with or without a prefix or two peeled first. No letter is ever dropped
  from the known side: the loose rule that ignored vav and yod on both sides is out.
- **Only on a token that came with points.** Haser is what taking the points off leaves;
  an unpointed page is written male already, and there the rule would only add
  collisions (קם for קיים). An unpointed page measures exactly as it did.
- **Measured locally, against the common words alone:** Genesis 40.0% to 43.6%, Ruth
  40.3% to 44.0%, Avot 50.8% to 53.5%; across the 102 pointed texts on the laptop's shelf
  the lift is 0.9 to 6.5 points, median 3.2. The 1948 declaration, unpointed, is 39.9%
  before and after.

What it does not touch: `coverage`, the figure on the library shelf and a built text,
which intersects dictionary forms and has no spelling problem.


### What we inferred says so — 2026-09-27

Everywhere targum has an answer it is not sure of, it has picked between two things: say
it flatly, or say nothing. `pronounce.sayable` refuses a word with no vowels because "a
wrong one is a lie told with confidence"; the roots, the Onkelos senses (a hand table and
a verse name, because spelling alone was 42–70% right) and the cast oracle stay silent
for the same reason. The pronunciation line on a word card goes the other way. Where the
text carries no mark for the stress, phonikud puts it on the last syllable, the card
prints that as fact, and it is right about two words in three. And on the modern shelf
the vowels it reads from were themselves put there by the menaked, not by the source.
There is now a third option: **the answer, shown, with "inferred" beside it.** David,
2026-09-27, targum-internal#323.

- **The first uses are the stress and the vowels, on the pronunciation line.** The
  reading is followed by the word "inferred" («выведено» in Russian; the interface's own
  word in each language it speaks) when the stressed syllable was guessed rather than
  read off a mark, or when the pointing came from the menaked rather than the source.
  The IPA itself is unchanged. A text whose vowels the source carried — the Tanakh,
  Sefaria's vocalized editions, Ben-Yehuda where the source pointed it — keeps its vowels
  unqualified; only its guessed stress can say "inferred".
- **Today that is every guessed stress, and it is shown now.** No stage in the build has
  a calibrated confidence on stress (#318 measured Jev and did not adopt it), so every
  stress phonikud defaulted says "inferred" — on modern Hebrew, most words. That is the
  honest state of the card, and it is shown as it is rather than held back until a better
  source makes it rarer.
- **Tapping "inferred" says what the text left unmarked,** on a line under the reading in the card's
  own quiet style: "The text doesn't mark the stress, so we inferred it.", "The text has no
  vowels here, so we inferred them.", or "The text marks neither the vowels nor the
  stress, so we inferred both." The same words are its accessible
  name, so a screen reader hears them without the tap.
- **What it looks like.** One word, in muted ink (§4), at the card's own size, after the
  thing it qualifies and outside it. Never a number, a percentage, a bar or a scale;
  never clay, sun or any hue that reads as a warning; no icon, no question mark, no
  italic. It is a word in a sentence, not a state.
- **What decides it: one bar, precision 0.95.** Where a stage has a calibrated
  confidence — measured in `evals/ledger.jsonl`, precision rising as the confidence does,
  as Jev's did on stress in #318 — the stage records, beside its ledger row, the
  confidence at which its measured precision reaches 0.95. An answer at or above it is
  shown plainly; an answer under it says "inferred". The bar is the same for every stage.
  Where no calibrated confidence exists, the only distinction is whether we guessed it or
  read it from the text, and every guess says "inferred". The bar lives in this entry and
  the thresholds beside the ledger, never on the page.
- **What never gets it.** Anything read off the text's own marks: a stress from
  phonikud's mark (U+05AB) or a placed Masoretic accent, the nikkud a source carried, a
  qamats qatan marked as one (U+05C7). Counts, which are not guesses: known share, words,
  time, days. And public pages: the landing says what the product does (§6), and
  "inferred" belongs beside the answer it qualifies, inside the product.
- **It only replaces silence or a flat assertion.** It may not be added where the answer
  is already certain, and it is not a softener for copy. A guess shown flatly today moves
  to "inferred" when its use is added here. Silence keeps a stricter rule: a guess that
  today shows nothing may come out only with a calibrated confidence and its threshold
  behind it. For anything with no number under it, `sayable`'s rule stands.
- **Each new use is an amendment to this entry.** A sense, a root, a cast, a guessed
  qamats qatan: each names its confidence and its threshold before a card says
  "inferred" about it.

The word was "probably" until David changed it the same day: "probably" hedges without
saying what was uncertain; "inferred" says what happened.

This fits the positioning, which shows the machinery to readers who want it, better than
silence did, and it keeps the voice: we say what we did, in one word, and do not
apologise for it.


### A figure on Your Progress that can fall — 2026-09-27

Every figure on Your Progress only rises, because every one counts marks; §12's entry on
the streak calls that "the property the whole ledger is built on". Dmitry Z asked
(2026-09-16) for "visible honest progress tracking", and a count that only rises cannot
say how reading actually went. So one panel, **What you knew of what you read**, draws the
share of the running words in each month's finished sections that the reader had marked
known on the day they finished each one — and it is allowed to fall.

What keeps it honest is that nothing recomputes it. A finished section is measured once,
when its row reaches the account, against the ledger as it stood that moment, and kept (the
`reading` table); a word marked today does not reach back and lift August. It departs from
"the server only hands over the page" for the reason Time and words does: it is the
account's reading of its own record, so it is absent signed out, and absent, not nought.

What it keeps to: said as a count in ten ("In August you knew about 7 words in 10 of what
you read"), never a percentage, a level or a score (§6); one hue, leaf, whichever way the
line goes, because a fall drawn in clay would be the verdict the page refuses to give. When
the latest month is lower, one sentence names the reason — the text had more words new to
the reader — without apology or encouragement. Under three months there is no line, and
the page says what would draw one. Nothing before it shipped is backfilled: the line starts
the day it lands, and the note says so. targum-internal#291.


### A post keeps its shape — 2026-09-27

A post pasted from Instagram arrives as a post, not as three paragraphs with a title
(targum-internal#157–#159). David chose Instagram first on 2026-09-27; X and TikTok follow
the same rules when their doors open. The shape is redrawn in targum's own type and
palette. The platform's chrome is not.

- **What is kept.** The author's handle, and their name and the day it was posted where
  the post gives them; the pictures in the post's own order, or its film; the caption. The
  caption is the text: segmented, tappable and translated like any other reader text,
  with its line breaks kept, because a caption's lines are how it was written.
- **What is not.** No platform logo, no platform colour, no like, comment or share button,
  no counts. A button that cannot act on the platform is a lie, and a count is a number
  about a moment that has passed. Hashtags and mentions stay where the author put them and
  are not glossed or counted as vocabulary: they are names, not words.
- **Where it sits.** The post's head (the author's picture, their handle, the day)
  takes the title's place at the top of the reader, and the pictures follow as a row the
  reader swipes, each 1:1 or 4:5 as posted, never cropped to a card. A reel is the film
  panel "A reader that carries moving pictures" (2026-08-31) already draws, at 9:16. The
  bar, the tap, the card and the audio are the reader's own and unchanged.
- **Nothing is fetched.** The pictures are carried in the page as webp data, as covers
  are, and so is the author's own picture, small, in a disc. Where the post gives none the
  disc is their first letter, as a text with no picture wears its letter on the shelf
  (David chose the picture over the letter on 2026-09-27). One link home, "On Instagram",
  is the one outbound address the post adds to the allowlist `test_render.py` pins.
- **Always private.** A post is its author's, with no licence granted: it lives on the
  reader's own shelf and nowhere else, never the catalogue and never the shared shelf.

Amended 2026-09-27 (targum-internal#158), for a reel: **a film's text is what was said,
and its caption follows it.** The head is the same head, the film is the film panel, and
the transcript is the rows the film follows. The caption the author typed is still text,
tapped and translated, but it is a second item under the transcript with "The caption"
named once where it starts — never above it, where it would be read as the start of what
was said and would push the transcript onto a page of its own. The head's "On Instagram"
is the film's one way home, and the bar's own link home gives way to it.

Amended again the same day, for a TikTok: **a TikTok is a reel's shape**, 9:16 in the
film panel, the transcript its text and the caption after it, and its head says "On
TikTok". TikTok gives no author's picture without a fetch of its own, so the disc wears
the first letter of their name.

Amended 2026-09-30, for a Facebook video: **a Facebook video is a reel's shape too**, "On
Facebook" in the head. Facebook gives a page's name and a number, and no handle anybody
knows a page by, so its head carries the name and the day and no "@" line; the disc wears
the name's first letter. A post brought by hand is not yet taken from Facebook: most of
what is posted there is words, at addresses the video door does not read.

And for X, the same day: **a post on X is a post's shape, and a thread is one post an
item**, each with its own photos under its own lines, in the order written, "On X" in the
head. The thread is read back from the post pasted to its start, then on
through the author's own replies as far as X shows them to somebody signed out, and it
stops at the first post by anybody else. X shows only part of a thread that way, so where
some of it may be missing the card says so under the head, "Some of this thread may be
missing. The rest is on X.", and never passes a part off as the whole (David asked for
the forward walk on 2026-09-27). The door is built and **shut** (`TARGUM_X`) until David arms it, because X's
terms forbid collecting its posts by automated means and the box fetching one is
targum's act.

Amended again the same day, for a post brought by hand (targum-internal#158; David chose
to build it on 2026-09-27): **a post targum cannot fetch is typed in, and arrives in the
same shape.** "Bring a post" on the Add page takes the box's place while it is open, so the
page keeps one filled button. It asks where the post was posted (Instagram, TikTok or X),
the handle, the name where the post shows one, what it says, its pictures in their order
or its one video, and its link where the reader has one. The link is kept only in its
platform's own shape; without one the head draws no way home. Nothing is fetched to fill
the rest in: no day, because nobody was asked for one, and no face, so the disc wears the
first letter of the name (an avatar upload was left out as one more field for a letter
that already does the job). A video is a film post, its transcript the text and the typed
words its caption. The pictures are drawn as brought; the words in them are read only when
the reader presses "Also read the pictures", the Instagram post's own press, charged the
same way. Private, like every post.


### A level that spreads, a Russian name, and a definition that steps back — 2026-09-27

A design and QA pass (targum#435) measured four things on the live shelf and put them to
David, who chose each (targum-internal#372–#375).

- **A text's level is read at 90% of its running words, not 95%.** At 95% the rung fell
  past wordfreq's list for nearly every real text: 153 of 186 levelled Hebrew texts read
  Vav · C2 and "On the bus", seventeen words, read Hey · C1. A list of spellings misses
  what a reader's lemmas are, and a label that says C2 of everything says nothing. At 90%
  the scenes land at gimel. The other tenth is what the dictionary one tap away is for.
  This amends "The shelf says what a text is at a glance" (2026-09-24).
- **In Russian the place is «Ваши тексты», and «Тексты» where «Ваши» drops.** «targum»
  alone, on a phone, was the wordmark's own word two inches from it, because targum is not
  declined. English keeps Your targums and targums. This amends "One name" (2026-09-25)
  for Russian only: one name in each language, not one name across them.
- **What's a targum? is whole until the reader has finished a text,** then one line that
  opens it. On a phone it was the first screen of every visit to a shelf of seventy.
  This amends "A targum is shown" (2026-09-26), which drew it always.
- **At a desk a letter tile is a strip (16:5); a picture keeps 16:9.** On a shelf of
  uploads most of the desk was beige boxes with one letter in each. This amends "At a
  desk the shelf is cards" (2026-09-26), whose letter still stands, smaller.

The series fold reads its title with pointing and direction marks left out, counts a
Hebrew numeral (פרק כג), knows S01E02 and a second marker ("Part 2 – Chapter 3"), and
asks a stem to be a name, two words or eight letters: "The" before "Chapter 11" is none.


### Your targums has tabs, says what a targum is, and folds a series — 2026-09-26

David, on Your targums at a desk: "I want this page to be designed more delightfully, and
easier to navigate. It should include tabs with 'all targums' 'your uploads' and
'playlists' also it should define a targum more clearly and prettily." Asked, he chose
each of the following.

- **Three tabs: All targums · Your uploads · Playlists.** All targums is everything
  "Yours and everyone's" (2026-09-25) put here. **Your uploads is only what you brought**
  — pasted, uploaded, photographed or linked — and not a Library text you built or a
  shared one you opened. A build in progress is in both. This does not bring back the
  Library's Your uploads tab: the Library is still everyone's, and this is a view of
  yours. Playlists is a link to /playlists, which carries the same three tabs with
  Playlists chosen and lights Your targums in the nav, so the three read as one place.
  Underlined tabs, as the Library's are.
- **A targum is shown, not only said.** The line "an interactive bilingual text,
  optimised for language learning" gives way to one sentence and a drawn example: a
  Hebrew line, its translation under it, and one word tapped, with its card. Drawn in
  type and the palette, never a picture file, so it costs the page nothing to fetch. The
  example is Hebrew whatever the shelf's language: Hebrew is the product's first language
  and the word it is named for.
- **The shelf can be sifted.** Chips for All · New · Started · Finished, each with its
  count and absent at nought (a pressed chip stays, at nought, while it filters); a search over the title and its English; and an order —
  last read (the default, as before), recently added, easiest first, or most known. They
  are drawn only on a shelf of six or more: on a short shelf they are questions nobody
  asked.
- **At a desk the shelf is cards; on a phone it stays rows.** The same row, laid out as a
  card from 64rem up, with the picture as its head. A text with no picture wears its
  letter large. Nothing a row says is dropped from the card.
- **A series is one row until you open it.** This amends "one row per text in each list"
  (2026-09-25). Two or more texts whose titles share a stem before an episode marker
  (*פרק 63*, *Part 2*, *глава 3*, *#4*) fold into one row with the stem as its title, how
  many there are and how many are finished, and a stack drawn behind its picture. Pressing
  it shows those texts alone, in episode order, with a way back. It is read off the title
  because nothing else says what a series is; a title that does not follow the pattern is
  its own row, which is what it was before. A search or a chip looks inside a series, and
  a series left with one text is that text's row.

What it does not overturn: a row still says the seven facts of 2026-09-24, a build is
still a row from the moment it starts, the trash is still at the foot, and Learn's cards
draw the same rows without any of this.

Amended 2026-09-27 (targum#435), from a design and QA pass: the chip says **Started**, the
word the row's own status uses, rather than Reading, so one state has one name. The tabs
stand under the heading and **above** the definition, so they are in the same place on all
three tabs (Playlists draws no definition), and a reader with nothing on the shelf still
sees the definition and the tabs. A row's press is its title, stretched over the row, so a
keyboard can reach it.


### The finished box is three figures — 2026-09-25

David, looking at the ink block a finished section inverts to: "let's review what info we
give at the end of each lesson". It held a sentence ("You finished a targum."), an ordinal
and a date ("Your 1st · Sep 25"), the ledger's increment as delta and standing for known
and saved ("12 newly known · 2800 known"), a reading-day or longest-run line, and three
lines of words — looked up here and how often before, read here without a look-up, and an
offer to keep two or three. Each was argued for on its day (#173–#175). Together they were
a paragraph to read at the moment a reader wants to move on. Asked, David chose: "literally
just a count, more mathematical, statistical, quick to scan"; this text only; lead with
the win "but keep it very clear — just scan with eyes and get the info"; and four equal
tiles over a single big number.

- **One line and three tiles.** "Finished · #14" on the first line, Undo on the same
  line. Under it three figures of equal weight, each with a two- or three-word label under
  it: **+N words known** (what became known while this section was read, the words the
  press marked included), **N% known here** (the header's own figure, taken after the
  press), and **N words looked up** (distinct words tapped for a meaning here). Serif
  tabular figures on the ink, as the ledger's figures always were.
- **A zero is shown as 0**, never hidden, so the three always stand in the same places and
  a reader learns where to look. "Lead with the win" is kept by the figures being wins or
  plain facts — nothing in the box is a verdict — and when nothing was won the count leads:
  finishing is the win.
- **This text only.** Standings — 2800 known, 140 saved, the longest run — live on Your
  Progress, which is where a reader goes to see a standing. A delta beside a standing is
  two numbers to reconcile; a delta alone is one to read.
- **Dropped:** the date (Your Progress keeps it), the sentence (the line says "Finished"),
  the saved count, the reading-day and longest-run line, and the three lines of words.
  The longest run is now said only on Your Progress, which amends 2026-09-03's "announced
  only in the delivered increment". The words a reader looked up are still counted, still
  kept under `targum:cards:<language>`, and still what Words draws from; they are no longer
  listed here.
- **A percentage is allowed here**, which amends #174's "never print a percentage": the
  figure is the header's "N% known here", already on screen, counted from real marks, and
  it is about the text, not a grade of the reader. "Score", "points" and "level" stay
  banned, and nothing on the block moves.
- **In a playlist it is said twice, briefly.** The line the reader lands on says the same
  three after the title: "Finished <title> · +12 known · 96% · 3 looked up · Undo". And the
  playlist's end card adds them up across the texts finished in it: texts finished, +N
  words known, the share known across all of them weighted by words, and words looked up,
  in the same tiles.

What it does not overturn: a section is finished once, the press is the reader's, Undo
takes back the finish and the words, and the increment is still drawn only where the
section is finished in place.


### The foot is one block — 2026-09-25

David, on a phone at the end of the second text of a playlist: "This positioning of buttons
at end of Playlist lesson does not feel intuitive to me." The foot of a section was three
things written on three different days: the playlist's line with Back and a teal Next
(#366), a strip offering the words never marked (the first alpha reader), and a leaf Done
that finishes the section (#173). They stacked in the order the code happened to append
them, so moving on came first and finishing came last, with two primary colours a screen
apart and a gap the player's margin opened between them. And Next finished nothing: a
reader who went Next, Next, Next through a set had finished nothing on Your Progress.
Asked, David chose each of the following; outside a playlist, "I never liked the two
button positioning (done + mark words) find a sleeker design for it".

- **One block at the foot, in reading order:** where you are, one press, one quiet way to
  press it differently, and what comes next. One primary colour, §13's pill.
- **The press says both halves.** "Done, and mark 12 words known" finishes the section and
  marks the words never marked, in one press; "Done without marking" under it, as a text
  link, finishes it alone. With nothing left to mark the button is "Done" and there is no
  link. Names and numbers are still cleared by the press and still never called words.
  "Offered, never done for you" stands: the press is the reader's, and it says what it
  does before it is pressed.
- **In a playlist the press is Next.** "Next, and mark 12 words known" / "Next" / "Next
  without marking", and on the last item "Finish" in the same three forms, followed by the
  end card. **Moving on finishes the section**, which amends #173's one Done per section:
  a section is still finished once however often it is pressed, but leaving forward is the
  press. A swipe forward, the arrow and the Next among a video's keys finish too, without
  marking: a swipe is a press (2026-09-23), and marking words is never done by a gesture.
- **Back is a small link on the line that says where you are**: "← Back · Couples and
  everyday life, 2 of 3". "Up next: <title>" is a small line under the press, not a second
  button naming the same place.
- **Undo is where the reader lands.** A press that leaves the page takes the reader to the
  next item, so the next page says, once and briefly, at its top: "Finished <title> · 12
  words marked known · Undo". Undo there takes back both, the finish and the words. Coming
  back to a finished section still offers Undo on its ink block, as it always did.
- **The ledger's increment is not drawn when a press leaves the page.** It is drawn at the
  foot of a section finished in place, as before (2026-09-03); a reader who has pressed
  Next is already reading the next thing, and the counts are on Your Progress.

What it amends: the separate Done at every section's foot (#173) and the separate offer
under the text become the one press. "Up next" shown only once finished (#173) stands
outside a playlist, where the door to the next section still appears after the press. What
it does not overturn: a section is finished once however often it is pressed, the finish
travels to the account, and the words a press marks are one Undo away.


### Yours and everyone's — 2026-09-25

David, on a phone, reading "It's on your texts too" under a build: *"there is some
redundancy with Library and with the Your uploads tab within that. Further, I don't know
if the user will understand intuitively the difference between library and texts."*

He was right on both counts, and §12 was the cause. "A build is on the shelf while it is
building" (2026-09-17) called the Library "the one page that can honestly say
'everything of yours is here'", and put a build under Your uploads. "The shelf says what
a text is at a glance" (2026-09-24) made Your targums a place in the nav, "where a reader
goes back to what they started". Both were true, so both pages listed an upload, drawn
two different ways, and one place went by three names: Your targums at a desk, Texts on a
phone, Your texts on Learn. And the wait page sent a reader to Texts to find a build that
was only in Your uploads.

- **Your targums is yours; the Library is everyone's.** Your targums holds everything of
  yours: what you built from the library, what you brought, what is being built right
  now, and the trash. The Library holds the texts targum offers everybody, and nothing
  else. **Your uploads is gone as a tab.** The Library's tabs are All texts, and the Beit
  Midrash for Hebrew.
- **A text you built from the Library is still marked in the Library.** Its row says so
  and opens your copy. That is the catalogue telling you which of its books you already
  have, not a second shelf.
- **A build is a row at the top of Your targums from the moment it starts**, with its
  title and how far it has got, and becomes the ordinary row when it is done. This
  replaces the same rule's home under Your uploads. The wait page, Add and the Library's
  own row still narrate it where the reader pressed.
- **One name: Your targums.** At a desk it is "Your targums"; on a phone and in a
  narrow window "Your" drops, as it does for Progress, and it is "targums". This
  retires "Texts": the 2026-09-24 worry that "targums" alone read as a typo is outweighed
  by a place with two names. Learn's cards and ⌘K say Your targums too.
- **The shared shelf stays in the Library.** The texts targum builds for everybody are
  targum's until you open one. Once this browser has opened one, it is on Your targums
  beside your own, with nothing on it to delete, because it is not yours to delete.

What it does not overturn: one row per text in each list; a build narrated where it was
pressed; the Library's filters and its band, which are for choosing and now have only
choosing to do.


### The grant is one press, and chatting is included — 2026-09-24

A design and QA pass over the connector and playlists found that the approval page and the
words around it had drifted apart. "A scope is a press that lasts" (2026-09-22) says the
press is the reader *ticking* the spending scope. The page never drew a tick: it grants
what the app asked for, in one press. Meanwhile /connect told strangers to "Tick what you
want", and every tab's steps said "choose what it can see". David, asked which one should
give way: **keep the one press.**

- **The approval page grants the scopes the app asked for, all together, in one press**,
  and says plainly what each one lets the app do. Connect and Not now are the only choices.
  To change what an app may do, you disconnect it from your account and connect it again.
  Nothing on /connect, in the FAQ or in the steps promises a tick.
- **Chatting is included.** A message rounds to zero credits ("A cost is credits",
  2026-09-23), so the reader is told it is included rather than "a few seconds of your
  credits". Credits are named only where audio or video is, with the rate beside the balance.
- **A Russian reader is promised Russian.** The Russian /connect says a Russian line
  under the Hebrew and asking in Russian, because the contract writes `= ` lines in the
  language the reader reads.

What it does not overturn: the spending scope is still the consent, the two ceilings still
hold, and the model still cannot press anything. The consent just covers the whole request
the app made, not a subset the reader picks, and the page has always done exactly that.


### The shelf says what a text is at a glance, and has its own door — 2026-09-24

David, looking at the shelf: it should tell the reader, without opening anything, the
text's name, how long it is to read or to watch, its level, when they added it, how much
of it they know, whether they have read it, and which playlists it is in, with a picture
where there is one. "Also we need an easier way for the user to quickly navigate to their
shelf." The shelf was reachable only from Learn's "All your targums", hidden when Learn had
no cards, and from ⌘K.

- **The nav is five: Learn · Your targums · Library · Your Progress · Add.** This amends
  "Add is a place again" (2026-09-13), which made it four. The shelf goes second because
  it is the second most visited: it is where a reader goes back to what they started. On a
  phone "Your" drops, as it does for Progress, and the bar takes five columns.
- **A row carries seven facts, in this order:** the picture; the title with its English
  under it; one line of facts (length, level, known share, and when it was added for an
  upload or last opened for a library text); its status; and, on the right, Add to
  playlist and a ⋯ for the rest (chapters, delete). The playlists a text is in are named
  on the fact line. On a phone the fact line wraps under the title, and status and
  playlists fold into it.
- **Length is what the text takes:** minutes to read, or the recording's own length for a
  video or a recording ("4 min video"), read from the manifest.
- **A text has a level, and it is the text's, never the reader's.** It is the ulpan rung,
  with CEFR beside it, whose vocabulary covers 90% of the text's running words, measured
  from word frequency (95%, the research's unassisted threshold, until 2026-09-27: see
  the entry of that date). It is not the tier count the library's Easier/Harder chips use. "Never tell the reader they are at a level" stands:
  the label says what the text needs, not where the reader is. A band is still not a CEFR
  level; a whole text's coverage is.
- **Known share is a percentage on the shelf**, as it already is on the library's cards
  ("You know 72%"). The count in ten stays on the press card, where it came from.
- **Status is three words:** New, a part count while reading ("3 of 6"), and Finished,
  with the leaf check that "Recently read" already uses.
- **A video import gets a picture:** one frame from its own cut, kept beside the reader
  and served like a cover. The letter tile stays for a text with no picture.

What it does not overturn: one row per text in one list; covers as the library draws
them; no counts of things watched; no level on the reader.

### The connector is a banner and a line in the foot — 2026-09-24

**This retires "A door that is not a text — 2026-09-22"**, below, which put targum in Claude
and ChatGPT into Learn's row of doors, styled exactly like the reading doors. It shipped,
David looked at it on the live page, and said: *"advertise the mcp in some other way, maybe
a separate button or a banner"* — and, asked where, *"Banner and it should be in footer"*.

The objection was written down the day the decision was taken, under Risks: *"a third door
where two carry texts. Learn's first job is getting somebody into something to read, and a
door styled identically but carrying a way in instead competes with the two that carry
one."* It was right, and what settled it was looking at the page.

- **A banner, above the row.** It announces something once, where a door goes on asking for
  ever. It is not in the row, so the row is things that carry texts again.
- **A line in the foot**, which is the permanent home: the foot is already where the things
  that are always true and rarely wanted live, and this is one of them.
- **It goes when it has been taken up.** Not a dismissal anybody has to remember — the
  banner is drawn only for a reader with no connection, which the account already knows. A
  reader who has connected is never asked again, on any device, with nothing stored to make
  that so. The cross is for somebody who does not want it *now*, and that one is
  per-browser, because it is a convenience and not a fact.

**And the doors are counted, which they never were.** The 2026-09-22 entry asked for "a look
at whether the reading doors' press rate moves after it ships". That look was impossible:
`learn.html.j2` never loaded `events.js`, so no door on this page has ever been counted and
the question could not be answered even in principle. It is wired now — the reading doors
and the banner alike, as `control` events, which carry a name and a window width and nothing
else. So this change is measurable and the one it replaces was not.

What it does not overturn: the row still decides on the reading doors alone whether it is
worth drawing at all; nothing on Learn pushes; and §6 still governs the words, so the banner
says what a reader gets rather than selling it.


### Asking to practise a language is how you choose it — 2026-09-23

David, in Claude, on the day the connector went live: *"Bonjour, je veux pratiquer mon
français. Est-ce que je peux faire ça avec Targum?"* — and was told no, because his targum
account was configured for Hebrew only. Two tools carried the same guard, `how_to_talk` and
`record_turn`: a language not in `Store.learning` was refused by name.

**The guard had it backwards.** Saying, in your own words, that you would like to practise
French *is* the reader telling targum what they are learning — a plainer statement than the
picker, because nobody opens a picker by accident. Answering it with the account's own
configuration makes the product argue with its reader about what the reader wants, and
points them at a page they are not looking at.

So the guard is gone from both, and the answer splits along the seam that already exists:

- **Talking is free and writes nothing.** `how_to_talk` hands over the contract for any
  language in `TALKED`, whatever the reader has chosen. The ledger comes back empty in a
  language they have no words in yet, which is true and is the point — there is nothing
  there to protect, because nothing is spent and nothing is kept.
- **The language goes on where something is already being written.** `record_turn` keeps
  the first line the reader writes and turns the language on in the same breath. That is
  the first moment anything of theirs is recorded, and it happens under `chat` — the one
  scope whose words on the approval page say it keeps what they write. That scope now says
  so out loud, and dropped the word "Hebrew" while it was there, which had stopped being
  true the moment French could be spoken.

What is still refused, and by a better test: a language targum cannot hold a conversation
in. Aramaic has no contract (#284), and the refusal names that rather than the account.

**`Store.also_learning` adds; it never replaces.** `choose()` writes a kind wholesale,
which is what a form submitting a set wants and the wrong shape here — a reader asking for
French has said nothing about Hebrew. There is a trap underneath it that a test found
rather than a reviewer: `_chosen` answers a person with *no* rows with the default,
`{"he"}`, which is almost everybody, because almost nobody opens the picker. Inserting one
French row beside that turns an implied Hebrew into an explicit French and drops Hebrew on
the way, silently. So the effective set is written down whole, the first time anything is
added to it.

What it does not overturn: ownership comes from `Ctx` and never from an argument; a build
still needs its own press; `REQUIRED_LEARNING` still keeps Hebrew on; and the model still
decides nothing — it passes on a line the reader wrote, and the reader wrote it.


### A playlist is swiped, and one press takes the set — 2026-09-23

David, the same day, after a connector found him twelve Hebrew reels and could not bring
them in: "Once in a playlist they can simply swipe into the next targum super fast, giving
almost an instagram like feel to it. They won't really even feel like they are learning."
For YouTube, articles, anything. The first stranger session (2026-09-03) said the product
feels like work; this is the answer to that from the other side — not less machinery, but
the machinery arriving one item after another without a decision in between.

It reverses two written rules and adds a thing a reader owns. Each is said here before any
of it is built.

- **A playlist is the reader's.** An ordered list of texts, kept on the account and not
  in the browser, with a name. Four hands make one: the connector, targum's own chat, the
  reader by hand (add to a playlist from any reader or shelf row), and targum, whose own
  sets — "couples and everyday life", "in the kitchen" — are built once on the shared
  shelf like the Khan Academy rows and cost the reader nothing to open. A playlist of texts
  already on the reader's shelf costs nothing either. This is not `series.py`: a series
  comes out on its own clock, and a playlist is a list somebody made.

- **One press takes a named set.** `video/youtube.py` refuses a playlist address with "A
  playlist is a queue of separate decisions", and until today every build was a quote and
  a press. A set now quotes as one: each item named, each with its length and how much of
  it the reader knows, the total in credits, and one press on targum's page that builds
  them all. That is still the reader's own hand on targum — "A scope is a press that
  lasts" (2026-09-22) is the precedent for a press that covers more than one job, and
  this one covers a list the reader can read before they press. What does **not** change
  is the harvest guard: a playlist, channel or feed *address* is still refused, because
  an address names somebody else's list, and the set is a list the reader (or a model on
  their behalf) wrote out item by item. Every item is still their private import and
  never the catalogue (#126). A set is capped, at twenty to start — the number is the
  build's to tune, the cap is not.

- **A swipe is a press.** "Nothing plays until pressed. Autoplay is the arcade's move"
  ("A text that carries media opens as its media", 2026-09-03) was written for a page
  that starts itself. Inside a playlist the reader's swipe
  is their hand choosing the next one, and the next one plays. Nothing plays on arrival
  — not from a link, not from the bell, not when a playlist is opened; the first item
  waits for its press like any text. A swipe back plays nothing new.

- **Inside a playlist, a video opens watching.** "A video text opens as its transcript"
  (2026-09-17) stands for a text opened on its own, where the reader came to read. A
  reader who swiped into a reel came to watch, so there it opens as the picture with its
  line on, the way a reel is watched, and one press puts it back to reading. An article
  opens as its text; the next item is past its end, so a long text is read before it is
  left, and a swipe mid-text scrolls the text.

- **The end offers more, once.** The last swipe lands on a card: the words met across the
  set, and one next set chosen for them, quoted like any set and built only on a press.
  It never refills itself. A feed that tops itself up is the Instagram habit that turns
  "does not feel like learning" into "does not feel like anything", and a quote that
  spends is not a thing that happens because a reader kept swiping.

- **Motion stays optional.** The swipe is a gesture, not an animation: under
  `prefers-reduced-motion` the next item replaces this one with no travel. And every swipe
  has a key — a visible Next and the arrow keys — because a gesture nobody can find is a
  control without a job.

What it does not overturn: a quote is information and the model cannot press it; nothing
that spends happens on a model's decision; engagement yes, arcade no — no counts of reels
watched, no streak for swiping, and the words met are the only number at the end.

**Amended 2026-09-25: a text joins a playlist whether or not it is made.** David asked
Claude, over the connector, to add a weather forecast to the news playlist it had just
quoted. The model could not: `add_to_playlist` took only texts already on the shelf, so
it quoted the forecast alone and offered to add it "once it's on your shelf" — a second
press, a second page, and a promise the model had to remember to keep. Now
`add_to_playlist` takes a link or a library id too. The text is quoted the way an item of
a set is, and its job joins the named playlist unclaimed. The press is still the set's
page, `/set/<id>`, and it claims only what is still waiting, so a text already made or
already being made is not charged again. Nothing here spends on the model's word: adding
is a quote, and the reader's press is the only claim.

### The connector talks by the contract — 2026-09-23

The connector shipped with one sentence for the host at `initialize`, and it said what the
tools were and nothing about how to talk. So a reader who asked Claude for something to
read in Hebrew was answered in English, about Hebrew: the conversation that targum's own
chat holds in Hebrew, graded to the reader's own words, did not exist on the one surface
where somebody else's model writes the replies. David asked for it on 2026-09-23 — "it's
about immersion".

**One contract, both surfaces, now in the other direction too.** `how_to_talk` hands the
host the contract targum's chat is given (`contract_for`) and the reader's ledger block
(`ledger_block`), free and read-only, and `mcp_http.INSTRUCTIONS` and the `talk` prompt
send the host to it. It is marked `Tool.elsewhere` and never offered to targum's own
chat, which holds that contract already.

**The contract is the library's; the words are the record's.** `how_to_talk` is offered
on the `library` scope, so every connected reader is talked to in Hebrew. The ledger rides
with it only where `record` was granted (`Ctx.sees_record`), and without it the
conversation is graded to the commonest words instead of the reader's own — the words and
the slips are what `record` says it shares, and a tool that carried them past the scope
would make the approval page a lie.

Three things differ, and only three, because the host writes the replies and there is no
page of ours to draw them. Since 2026-10-06 the contract a host is handed says them in
its own sentences (`hebrew.for_connector`) rather than in a note above it that overrode
one, which a host was seen to ignore; targum's own chat is handed `contract_for` as it was:

- **The translation is asked for, not shown.** On targum's page every `= ` line is
  folded and a tap opens it. A host cannot fold, so an unfolded line under every Hebrew
  line would be the in-app conversation with its folding taken away, and the reader
  would read the English. The tap here is the reader asking: the `= ` line is written
  for the lines they ask about, or for all of them once they ask for that. A new word
  still gets its meaning, once, after the reply.
- **The recast is targum's.** Where the scope that spends is granted, every line the reader
  writes in the language goes through `record_turn` before the host answers, and the
  recast it returns is the `> ` line — the host's own correction is never shown as the
  record's, which is §12's "The host's correction is never the record" read from the
  page's side.
- **A door is a link.**

What it does not overturn: never a level; the length; the vocabulary; the host is still a
host, and a host that ignores the instruction is not something targum can stop. The
contract is the best a server can do, and the in-app chat stays the one place it is
guaranteed.

### A cost is credits, and a credit is a minute — 2026-09-23

Two entries below say a cost is hours. "Price language left the product the same day — the
reader pays by the month, so a wait is a time and a cost is hours" (2026-09-13), and "hours
said in hours and never in money" (2026-09-22). **Both are retired here.** What replaces
them: **a balance is credits, and one credit is one minute of audio or video.**

The hours language broke in two ways, and only the first is a bug.

The first is grammatical. "Hours" was doing duty as the pool's name *and* as a unit, so any
cost under an hour put the two in one sentence. The press card for a one-minute video read
**"Uses 1 minutes of your hours"** — a plural error and a category error in six words, which
is what prompted this. That alone would argue for saying minutes, not for a new noun.

The second is what actually kills it. Hours described the pool truthfully while the pool was
only audio: a recording transcribed on the way in, speech synthesised on the way out, both
things this product buys by the clock, and `serve.UPLOAD_SECONDS` sums them in seconds. Then
a written line of Hebrew began drawing on the same sum — charged, through
`hebrew.seconds_for`, as the time it would take to say aloud. That conversion is defensible
and it is invisible, and a reader told that writing a sentence costs them hours has been
handed a rule they were never given. The pool stopped being hours before the word did.

**Credits, and not minutes, and the argument against was heard.** A credit is a minute, so
the name carries no information a minute did not: "1 credit" must be taught where "1 minute"
is already known. It is taken anyway, for one reason — a credit is a quantity the reader
*holds*, and a minute is a duration a thing *has*. The pool is no longer a pile of durations,
and the moment anything is priced that has no length, "minutes" fails exactly the way "hours"
just did, while "credits" does not. The rate is the promise, not the unit:

> 480 credits a month — 8 hours of audio or video.

**The rate is shown wherever a balance is, never only on the pricing page.** A credit that
has to be converted from memory is the invented currency §6 forbids; a credit with its
equivalence beside it is a minute with a better name. So the account page says *412 credits
left this month — about 6 h 50 m of audio*, and the pricing page says both numbers in one
line. Cost points may say the credit figure alone, because the balance they sit beside
carries the rate.

**A chat message rounds to nothing, and that is the honest answer rather than an oversight.**
Eight words is about five seconds, which is under a tenth of a credit, and rounding it up to
one would overcharge by twelve times for the privilege of showing a number. So chatting
shows no per-message cost and the copy says it plainly: chatting is included. It is still
metered — `Library.claim_turn` passes the same seconds into the same monthly sum, so somebody
who talks for hours genuinely spends them — and the daily rail stays what its own comment
already calls it, a rate limit and not a ration. Metered, and free at the scale of a message:
both true, and the page says the second.

**The word is chat.** "Checking your Hebrew" was the scope name `check` leaking out of
`oauth.py` into the reader's copy. What the reader is doing in Claude or ChatGPT is having a
conversation, the in-app surface has always been called the chat, and the rail is already
`kind="chat"`. The scope is renamed with the copy; one word in the product, the record and
the rails.

Nothing in the rails moves. `UPLOAD_SECONDS` is still the ceiling, still in seconds, still
8 × 60 × 60; 480 credits is that number divided by sixty. This is a vocabulary, and a
vocabulary change that altered what anybody is charged would be a second decision wearing
the first one's clothes.

What it does not overturn: §6's ban on invented currency, which is about **engagement** and
still forbids XP, points and levels outright — a credit is what a subscription buys, not a
score, and nothing may be earned, awarded or levelled up; there is still no money anywhere
inside the product, and the reader still pays by the month; a wait is still a time, in
minutes, because a wait is not a cost; and the reader is still never charged for a turn
targum did not buy.

### A language talks once it has a number — 2026-09-23

French, Russian and Yiddish were given talk contracts on 2026-09-22 and all three went
into `hebrew.TALKED` together, on the decision that one contract serves both surfaces:
a contract that applied on the connector but not in targum's own chat would be two
standards wearing one name. That stands, and this does not reverse it.

What it adds is the thing that decision left unsaid. `TALKED` is read by
`session.mode_for` and no flag touches it, so a language put there converses in the
ordinary product on the next deploy — not only through the connector, which is
flag-held. A language arriving in that set is therefore a release, and it should carry
what a release carries.

The three were measured the next day, 200 sentences each against a professional
translator's rendering. French scored 41.5% and Russian 35.0%, against the Hebrew
contract's 9.0% on the same corpus and the same judge. Yiddish returned no recast line
at all about a third of the time, where the other two returned one every time, and the
rule that closes its contract tells the model to prefer common words from a list that
does not exist, because wordfreq has none for Yiddish. It has no judge number.

So Yiddish came out again, into `hebrew.HELD`: written, kept, and not spoken. The
contract is good — it writes real YIVO, pointed, and refuses daytshmerish, which is the
hard part of Yiddish and the part a model gets wrong by default. What it has not shown
is that it answers every time, and a conversation that fails a third of the time is
worse for a learner than one that was never offered.

The rule this leaves: **a language enters `TALKED` when it has a number, and the number
is what the reader will actually meet.** A contract may sit in `HELD` indefinitely
without costing anybody anything; a contract in `TALKED` is something a reader is
handed. `CONTRACTS` may therefore hold a language `TALKED` does not, and never the
reverse — a conversation with no rules is the failure that ordering prevents.

What it does not overturn: one contract, both surfaces; Aramaic stays out on its own
grounds, which are a decision about the register and not a measurement (#284).

### A scope is a press that lasts — 2026-09-22

Until now the rule was absolute and written in two places: a chat tool never spends, and
the press that starts a build stays on the page where the card is. `connector.py` says why
— "a client whose consent UI targum does not control would otherwise be a way round
`Library.claim`" — and CLAUDE.md says the same thing from the other side. `Tool.spends` and
`Tool.needs_consent` were drawn on 2026-09-05 for a surface where that might stop holding,
and never set.

The surface arrived. targum reached through Claude or ChatGPT (targum-internal#80) is worth
building because the record fills there too, and the record only fills if something recasts
what the reader wrote — `slip` is written by a model's judgement or it is not written at
all. A connector that cannot spend cannot check a line, and a connector that cannot check a
line is a read-only window onto a moat it does not deepen.

So **one tool spends, and the consent is granted once rather than pressed each time.**
`record_turn` takes what the reader wrote, targum recasts it on its own model against its
own contract, and the row is written. The press is the reader ticking the `check` scope on
targum's own approval page, where what it costs is said in hours before anything is
granted, and where it is revoked. *(Amended 2026-09-24: there is no tick. The press
grants what the app asked for, in one go, and chatting is said to be included — see "The
grant is one press, and chatting is included".)*

What makes that safe is not the grant. It is the two ceilings it sits inside — the reader's
own `CHAT_BUDGET` and the eight hours, both unchanged, both already refusing in words — and
a rate limit per token. Build them with the tool, not after it.

- **Only a line in a language the reader is learning is recast**, so a question asked in
  English spends nothing. The turn is a `job` row of kind `chat` through
  `Library.claim_turn`, on the same rails and the same `SUM(length)`. No second counter.
  In front of the claim sits a rail that can only say no (`chat/rail.py`, 2026-10-02,
  targum-internal#324): a line carrying the contract's marks, a link, code or a menu,
  mostly another script or another language, or one word said over and over is not the
  reader's own, and nothing is claimed. A fault in it is a no.
- **The host's correction is never the record.** It writes what the reader wrote; targum
  judges it. One table, one judge, one standard — which is the whole reason the re-check is
  worth paying for rather than trusting what comes back.
- **A build still needs its own press.** Nothing here touches that seam: a quote over MCP
  is still information, and it now carries a link to a targum page with the button on it.
  The model still cannot press anything, anywhere.
- **Elicitation is refused.** The protocol can ask the reader a question mid-tool-call,
  which looks like the missing consent surface. It is the host's UI, and a host that
  implements it badly would be deciding whether money moves. Consent is targum's page.

What it does not overturn: ownership comes from `Ctx` and never from an argument; no
invented currency; hours said in hours and never in money; the reader is never charged for
a turn targum did not buy. *("Hours said in hours" was retired on 2026-09-23 — a cost is
credits, and a credit is a minute. The rest of this line stands, and so does the scope
being renamed from `check` to `chat` by that entry.)*

### A door that is not a text — 2026-09-22

*Retired 2026-09-24 — see "The connector is a banner and a line in the foot" above. The
door came out of the row; the reasoning below is kept because the alternatives it weighed
are the ones the replacement had to answer.*

Learn's row of doors has been two since 2026-09-06, and they are registers: Modern and
Biblical, each carrying its own next text, its own progress and its own share of words
known. The code says what the row means — "the track is the register, never a level" — and
everything in it has so far been something to read.

It now holds a third that carries a way in instead: **targum in Claude and ChatGPT**,
styled exactly like the other two. Note 19 of 2026-09-22 asked for the invitation to be
prominent on Learn, and the alternatives were both worse — a dismissible card on a page
whose own panel promises "still pull and never push", or the account page, where nobody
finds a feature.

Styled the same is the decision and not an oversight. A door drawn as a lesser thing reads
as an advertisement, which is what the page must not carry; drawn as a door it is what it
is, a way in, and the reader chooses between three doors instead of two.

**It is appended, never counted.** The row is drawn only when there are enough reading
doors to be worth one, and that rule still reads the reading doors alone. A row holding
nothing but the way into Claude would be the first thing a new reader met on a page whose
own panel promises to pull and never push — an advertisement standing where a text should
be. So it is permanent in the sense that matters, never dismissed and always there, and
it is there only where there was already a row.

It is also the one door that is a link rather than a button: it goes somewhere, where the
others swap the sheet below, and it is never marked as the way the sheet was reached
because it never is.

The cost is real and is written down here so it is not rediscovered: Learn's first job is
getting somebody into a text, and a third door competes with the two that carry one. The
only signal that would say so is whether the reading doors are pressed less after it ships,
and the `event` rows are where to look.

### The arrival asks which language first — 2026-09-20

"How in on-boarding does the russian user switch to russian?" David asked, and the honest
answer was that they did not. An account's `reads` decides two things — the language of
the line under each Hebrew one, and the language the desk speaks (§13) — and a new account
was English in both. The ways out were the profile page, a question the conversation asks
once and only of a browser that already says Russian, and the operator marking an invited
address beforehand. The front door had a switcher, and what was pressed there was dropped
at the next link: the sign-in page went back to the browser's language, and the phone of
an olah who reads Russian is as often set to Hebrew or English.

So the arrival is **three questions, a screen each**, and the first is *What is your
native language?* — David's wording, the same day, over "Which language do you read?": it
is the question a person answers without thinking, where the other asks them to work out
what targum means by reading. What it sets is unchanged — `reads`, so the line under the
Hebrew and the desk. A reader whose native language is neither has a third row, **Other ·
Другой**, in both languages because it is nobody's own name: it sets English, the only
other language there is to read into, and it is an answer, so they are not asked again —
Skip says "not now", and this reader means "neither". This amends "The arrival is two questions" below in its count and in nothing
else: one question a screen, where it is said in words, a Skip on each, a Back on all but
the first, and the last answer opens the text.

- **First, because it is the one that cannot wait.** A reader who cannot read "What are
  you interested in?" cannot be asked it.
- **Asked in every language it offers at once.** The question a line a language, each row
  in its own name — English, Русский — and each marked as what it is. It is the one screen
  that may not assume the page's language, so its words are in `learn.js` and not in the
  catalogue. No flags: §10 stands, and the language menu's exception is the menu's.
- **Pressing a row is the answer**, as on the ladder. The account is told the way the
  profile page tells it, and the page is loaded again where the answer changed the
  language it should be in, because the server draws a desk page in one language. It
  comes back on "2 of 3", with the language one Back away.
- **Asked of everybody who has never said, and of nobody who has.** Not only of a browser
  that says Russian: that is the wrong signal for exactly the reader this is for. An
  account with `reading` rows has said — its own, or the operator's mark; so has a page
  that arrived in another language, a browser that holds a choice, and a reader the
  conversation asked. `first.js` and the arrival keep the same two keys, so neither asks
  after the other. `/account/me` says `readsSaid`, because `reads` answers English for an
  account that has said nothing and the two have to be told apart.
- **A press on the front door is a press.** The switcher's choice rides the sign-in link,
  the sign-in page and its email are in it, `signin.js` keeps it as what the browser reads
  into, and Learn hands it to the new account — once, at the arrival, which is the one
  moment it is certainly a new reader's. Only what was pressed is carried; a language the
  browser merely suggested is used and not kept.
- **The first text is one with their language under it, where there is one.** The shelf is
  English throughout and Russian in places (beta), so the arrival looks across all three
  subjects for a text whose `targets` has the reader's language before it makes its
  ordinary pick. Where none has it, the ordinary pick, in the language it exists in: a
  Russian desk over English lines, which is the true state of the shelf and the argument
  for translating more of it. Nothing is translated on the way in — no spend on a press
  that did not ask for one.

`test_learn_arrival_language.py` holds the rules; `test_pages_browser.py`'s arrival answers
the language first, and its walk into a text is six presses where it was five.

### A reel at the size a reel is — 2026-09-20

A design review of the arrival, the vertical film and Learn, at 320 to 1920 wide. Most of
what it changed is a repair and needs no entry. Three things are decisions, and would be
"corrected" back by somebody reading the older entries.

- **The fixture films were too small to fail.** `tiny.webm` is 64x36 and `tall.webm`
  36x64. Watching is a grid, a grid track left `auto` is sized by what is in it, and a
  reel comes down 480x854: the picture made its own row 2562px tall on a 900px window,
  with the line and the transport under the fold, and a landscape film did the same in
  any window shorter than it. Every test of the mode passed. `reel.webm` and `film.webm`
  are the sizes the importer keeps, and `test_reel_browser.py` lays them out at six
  windows. A layout test wants a fixture the size of the thing.
- **An upright film in a wide window has its line beside it, not over it.** "Laid over
  the picture in landscape" (2026-09-03) is right for a film that fills the window. An
  upright one is a column in the middle with a letterbox each side wider than itself,
  and the line and the transport were both laid across that column: two thirds of the
  picture on a phone turned sideways, and at any size the place a reel burns its own
  captions in. So: the film at the start, the line next to it as text on the letterbox,
  the transport under the line, and the tap that plays the size of the picture. Portrait
  is as it was — picture, line, transport, down the window.
- **A docked reel on a phone is an occupant of the band**, full width like any other,
  the picture in the middle of it and its keys down the edge. It was an 11rem box in the
  corner with the page showing beside it, and in a Hebrew text the corner it took is
  where every line begins. At a desk the upright dock is 13.5rem, as wide as its keys
  need, and the grip drops its word there and nowhere else (2026-09-14, "The picture's
  keys say what they do", stands for the other three).

And on the arrival, inside what 2026-09-19 settled: the question is set as a card title
at a desk as it already was on a phone — it was the size of the hint under it — and at
48rem the ladder is two columns of four, read down then across, because eight rows put
the text "somebody who ignores it still has" under the fold at 1440x900. Not now, on the
words-you-know panel, stands at the panel's head rather than under its fifty rows.

Three more the same day, each asked for by David after the review named it.

- **The build measures a film, so the page need not wait for it.** The shape came from
  the film's own metadata (2026-09-17), which is right and late: until it landed a reel
  stood in the stylesheet's 16/9 and then jumped upright. `tools.frame` reads the cut's
  size, `ManifestPart.frame` keeps it, and the page carries it as `tall` in the panel's
  class and `data-film` beside it. An attribute and not a `style`, because a served
  page's policy allows no inline style. A manifest from before today has no measure, so
  the render asks the cut on the disk, and a reader rendered again is put right without
  being imported again. The film still has the last word when it arrives.
- **The second question has a Back.** "One question a screen" stands, and so do Skip
  and the five presses. But the arrival went one way only, and a reader who pressed
  Next a subject early could not see what they had chosen. Back is a ghost beside Skip
  on the second screen and nowhere else; the subjects are as they were left, and Next
  keeps them again if they change.
- **Mark known, and None.** The two presses under the words-you-know list said "Mark
  checked as known" and "None of these", which §6 already called long ("a button or a
  link is one or two words"). On a phone they would not share a row beside the pill, so
  the strip stood two rows tall over a list with three rows showing at 320x568.

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
### The Beit Midrash comes back, as a way of walking the one list — 2026-09-19

"It is time to build the 'Beit Midrash' section," David wrote: another tab after Your
uploads, only for Hebrew, inspired by Sefaria's navigation, so that "someone who only
studies Biblical Hebrew should be able to find what they are looking for right away."

There was one before, and it was taken out. The catalogue was two shelves with a switch
between them and two sets of addresses, and "a reader had to know which room a text was in
before they could find it, which is backwards for the one page whose whole job is finding
something." What survived was the tagging (`catalogue.Tag`, `beit_midrash()`), kept so
that the texts a reader came for could one day be shown alone. `test_pages.py` forbade
the name on the library page, and `test_hosted.py` still refuses the old addresses.

So the name returns and the shape does not. **The Beit Midrash is not a second room; it
is the one list asked a different question** — not "what is it about" but "where does it
stand". Every text in it is also a row under All texts, at the same address, drawn by
the same code; `test_library_js.py` pins that, and the old test now asserts the invariant
it was protecting rather than the absence of two words.

It lives inside the rules that were already here:

- **"The list stays one list"** (The library folds, 2026-09-01). A door narrows the list
  the way a subject does, and the search still looks behind every door at once.
- **"A collection is not a second layer and must not become one."** Behind a door the
  collections are the ones the list already folds into, drawn by the same rows and
  cards — and standing **open**, because Sefaria's shape is every book under its
  heading, and a student looking for Ruth should not have to guess which of three shut
  rows it is in. The tab, Tanakh, Ruth: two presses.
- **"A row of chips is drawn from the rows that exist"** (2026-09-17). Seven doors —
  Tanakh, the Torah by portion, the Aramaic translations, Mishnah, Halakhah, Thought and
  ethics, Liturgy —
  and not Sefaria's dozen: there is no Talmud and no Midrash on this shelf, and a door
  with nothing behind it is a dead end. Each door carries its count.
- **Hebrew's alone** (§13: what only Hebrew has hides under another language), and drawn
  only where the catalogue says which door anything stands behind (`Collection.door`).

Two things it does that the rest of the library does not, each on purpose:

- **The level band does not apply.** All texts opens on what a reader can read now. A
  tree that hid the Writings from a beginner because they are hard would be a tree with
  branches missing; the reader came to see where things stand, and each row still says
  how much of it they know. The same reasoning took the band off Your uploads *(a tab until 2026-09-25)*.
- **It crosses a language line, at one door.** The Targums are Aramaic rows and have a
  door here (David, 2026-09-19: Sefaria files Targum under Tanakh, and a Torah student
  looks for Onkelos beside the Torah). They open as Aramaic readers, their words still go
  to the Aramaic list (targum-internal#202), and the door says what they are — "Aramaic
translations" under תרגום — because the Latin word is the product's name and §2 keeps it
lowercase and for the product alone. Nowhere
  else does the Hebrew shelf show another language's rows.

The tree has an address — `#bm`, `#bm/tanakh` — the first view of this page that does,
so a link can land somebody on a door. targum-internal#68, the account preference that
shows *only* these texts, is a different thing and still unbuilt; it was renamed the same
day and will read this tab's predicate. targum-internal#340.
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


### Three moments in ten minutes, and none of them is a tour — 2026-09-19

David, in the handwritten notes of that day: onboarding should "aim for a 'magic moment'
within 1 minute, another within 3, another within 10", and "the user should have a clear
understanding of all USPs within 10 minutes."

There was one first-run device in the whole product: a line under the reader's bar, "Tap a
word to say how well you know it", and a sentence on the first word's card. Nothing told a
new reader the page could be heard, and the first stranger never found out. And there was
one recorded failure: a tour that opened a word's card on load, which failed eleven
browser tests on "element is not stable" — "a card that seizes the band before anybody has
touched anything is not a tour, it is a page rearranging itself."

So the rule for all three: **a line said once, in place, in answer to something the reader
just did.** No overlay, no step counter, nothing that moves the page unasked, nothing that
leaves the page (Dmitry, 2026-09-16: any notification is fatal), and celebration in type
(§1).

1. **The word, within a minute.** As it was. The arrival opens a text directly
   (2026-09-19, above), and where the reader's subject has a text that can be heard, that
   is the one it opens — because the second moment is impossible on a silent page. A
   reader who named a rung and no subject is routed the same way (2026-09-27).
2. **The voice, within three.** When the first word is marked, the same line, in the same
   place, at the same height, says "Now press play. The page follows the voice, line by
   line." The press puts it away, and it is said once in a browser.
3. **Being remembered, within ten.** The first time What to work on has anything in it, it
   says what it is: "These are the words you marked. We keep them here, and they'll be
   waiting whenever you come back." One visit, and never again. It counts nothing — the
   fold's rule that nothing puts a number on what is waiting is untouched.
   And before that, on the page itself (David, 2026-09-27): the first time a section is
   finished in place, the offer under the ink block — the next part, or the next text —
   says how many of its words the reader already knows, the words the press just marked
   among them: "You already know 14 words in this one." A count of words, never a share;
   in the offer's own row, under its name, so nothing above it moves; said in answer to
   the press and never on load; once in a browser (`targum:taught-the-share`). The number
   is counted by targum's own server and only the number comes back (David on
   targum#476): a page on the shared shelf is built once for everybody, and no list of an
   offer's words reaches the browser. Nothing is said signed out, off a disk, where the
   offer cannot be measured or the count is nought, and the moment waits for a finish
   that has something to say. Not in a playlist, where the press leaves the page. The ink
   block's figures stay this text's own.

What is not here yet, and is the rest of the list David settled the same day: bringing your
own, talking to targum, and "targum remembers what you're having trouble with", which
waits for the events of targum-internal#127. targum-internal#335.
### Time and words on Your Progress, read from the account — 2026-09-20

"I believe we should track hours and minutes a user has listened and watched, and words
read," David wrote; "this data should be displayed and filterable on Progress."

Nothing measured any of the three. The audio store kept one resume position a text, and
nothing counted a word as read. So there is a record now of what happens in a text
(targum-internal#127: a word looked up, a stretch played, a page turned, a section
finished, where a sitting stopped, a control pressed), and Your Progress has a panel,
**Time and words**, that is a reading of it.

Two things about it depart from how this page was built, and both are on purpose:

- **It is not drawn from this browser's store.** Everything else on Your Progress is —
  "the server only hands over the page". These three figures are the account's reading of
  its own log, because the log is appended and never merged: `/sync` is last-write-wins,
  which is why a day's count is a constant 1, and a tally of seconds written from two
  browsers would be destroyed by the merge that keeps the word list whole. Read from the
  account, a phone and a laptop add up by construction. The cost is that the panel is
  absent signed out — **absent, not nought**: where there is no record the panel is not
  drawn, and where the reader has stopped theirs one quiet line says so.
- **It has filters, on a page that had none but the language.** What the reader was doing
  (reading, listening, watching) and when (all time, thirty days, seven). They narrow
  these figures and nothing else: a day is not in a language and the longest run is not
  in a medium, and the ledger above is untouched.

What it keeps to: real counts of real things (§6) in the ledger's own treatment — hours
and minutes, words, the reading face with tabular numbers — no unit invented, no hue,
because these are counts of what was done and not achievements, so leaf is not theirs. A
figure that is nought is not drawn. **A word is read when its page was turned past or its
section was marked done**, and the panel says so under the figures: never a guess from how
far somebody scrolled. Counted by the line, once in a visit, so a window resized cannot
count a page twice. Time is wall-clock, and a film played with its picture put away was
listened to.

The record itself stands behind `TARGUM_EVENTS`, off unless the deployment says so: the
privacy notice names a legal basis for every category of data, this is a new one, and
the sentence that says so is David's to publish. On the account page the reader has what
was decided — a plain account of what is recorded, a switch that stops it, and an erase
that asks twice. targum-internal#127, #339, #341.


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
  mattered. *(Since 2026-09-25 that page is Your targums, and a build is a row at the top
  of it. See "Yours and everyone's".)*

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

*Amended 2026-10-05 by "A video stands beside its transcript, or large" (#422): it still
opens with its transcript on the page and the picture on, but beside it or large rather
than docked, and there is no full-screen mode of its own. A vertical film is still
vertical, by the same `--film`.*

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
  and filter are "Which Hebrew"; the tabs are All texts and Your uploads *(All texts alone since 2026-09-25, with the
  Beit Midrash for Hebrew: see "Yours and everyone's")*. The weekly's
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

*Superseded 2026-10-05 by "A video stands beside its transcript, or large" (#422): the
picture no longer stands in a corner, and has neither grip, size key nor a full-screen
mode of its own.*

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

So the nav is four: Learn · Library · Your Progress · Add. *(Five since 2026-09-24: Your targums is second. See "The shelf says what a text is at a glance".)* Add is last because the order
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

*Superseded 2026-10-05 by "A video stands beside its transcript, or large" (#422): the
picture no longer stands in a corner, and has neither grip, size key nor a full-screen
mode of its own.*

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
75rem, where the bar has no room for a word (measured: at 1100px it cost a second row). Since
2026-10-05 the bar is one row and Keys is behind ⋯ at every width, a row named Keys ("The
reader's bar is one row", above). What a
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
is drawn only while the voice has a price — an unpriced voice is not for sale, which is
the decision of 2026-09-10, and `speech.priced()` is that condition in code.

*It has had a price since 2026-09-13 (`speech.PRICES`), so the door is on the page: a
Hebrew section with no recording of its own offers it, with the minutes beside it. This
paragraph said the door "is not on any page today" until 2026-09-20, three weeks after
it was.*

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
  stranger can say about the page is that it can be heard. *Reversed 2026-10-05 (David,
  targum-internal#421), see "The reader's bar is one row": the bar's ▶ Listen is now the
  named thing that says so, and the strip stays away until it is pressed. The aim — a
  stranger knows the page can be heard — stands; it is said once, in the bar.*
- **A text with video opens with its picture on.** The toggle stays, so the picture can be
  put away; the default reverses. *Carried further 2026-09-03, see "A video text opens as
  video" above: the picture is not on beside the page, it is the page until the reader
  says otherwise.*
- **Nothing plays until pressed.** Autoplay is the arcade's move, and a reader on a train
  is still a reader. *Amended 2026-09-23, see "A playlist is swiped" in §12: inside a
  playlist a swipe is the press, and the next item plays.*
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

*The band below was retired on 2026-09-27 (above): the picture now stands beside the
headline as a card. The rule about what the picture may be is unchanged.*

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
is hours. *(Superseded 2026-09-23: a cost is credits, and a credit is a minute. A wait is
still a time, and there is still no price inside the product.)*

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

