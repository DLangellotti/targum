# English copy audit

Branch `copy-audit`, from `origin/master` at 92027c5, 2026-09-28. This covers the English
user-facing copy inside targum and in every email it sends. The standards are David's
brief and `design.md` §6, with the §12 decisions left standing. Open decisions are in
`COPY_QUESTIONS.md`. The voice and terms are in `COPY_VOICE_GUIDE.md`.

## Pass 2 — David's answers applied (2026-09-28)

This branch was rebased onto master after #535 (the welcome, the waitlist's per-step
pages, the sign-in foot) merged. #535's `waitlist.note.*` keys and their Russian are
final. Two of its lines were corrected before it merged, in coordination with that PR:
- "This link no longer works" replaces "has expired". Waitlist links have no age limit.
- Joining now says an email went out only if the address wasn't already on the list.

**In this PR (wording):**
- **Q1:** the 38 stale Russian lines are rewritten and stamped. `test_strings` passes.
- **Q12:** the set page says unticked texts come out of the playlist.
- **Q13:** "The library still opens" replaces "is always free" in five refusals. The From
  targum playlists say "Opening them uses no credits". "That's a lot to build at once" is
  now "to get ready".
- **Q14:** the look on Add is no longer priced. Three orphaned keys are deleted.
- **Q15:** the /connect FAQ says "Chatting is included in your monthly credits. A new text
  you ask for uses credits, and you confirm it first."
  - *Changed from the approved text:* the recommendation said "Chatting uses no credits".
    That is false, because a turn is metered into the monthly pool (§12 2026-09-23).
  - The approval page keeps "Chatting is included" with no allowance named, as §12
    2026-09-24 requires (and `test_oauth_serve` holds). The model-facing `record_turn`
    note says the same thing.
- **Q16:** "More than 500 texts and videos". The catalogue has 532 Hebrew entries.
- **Q17:** the privacy notice gains:
  - clause 3.10 (the waitlist and the digest)
  - the ten-minute connect cookie
  - OpenAI, ElevenLabs, Google (spoken audio) and DataImpulse as processors
  - Resend's full list of mail, and Anthropic's chat and pictures
  - five US processors in the transfers clause
  - `LEGAL_CHANGED` set to 28 September 2026

  Clause numbers 3.1–3.9 are unchanged, so no cross-reference moved. Google sign-in is
  left out: it isn't configured on the box (`deploy/box.env.op`).
  **Confirm before `legal_is_public()`:** the legal entity names (OpenAI OpCo, LLC;
  ElevenLabs, Inc.; Google LLC) are from public knowledge, not from your contracts, and
  DataImpulse's entity and country are unstated.
- **Q18:** the consent line in `oauth.SCOPES` and the catalogue now reads "Send us what you
  write in a language you're learning, for us to correct. Add texts to your playlists, and
  get new ones ready for you to confirm." The line under it now carries "add that language
  to the ones you're learning".
- **Q19:** /you says to email hello@targum.page to take back a deletion.
- **Q24:** "Following" for series, and "Your profile" for /you.
- **Q25:** "Save as a text".
- **Q26:** the /connect kicker says "targum", not "targum Connect".
- **Q27:** the sign-in page h1 is "Sign in to targum".
- **Q29:** the ulpan and CEFR ladders say what they are. "Learned on targum" has a tooltip.
- **Q30:** "Unsubscribe" in both mail feet.

Every changed or new key has Russian, and each is stamped. design.md §12 has one dated
entry recording the five answers that undo earlier §12 names or silences.

**In the stacked follow-up PR (behaviour):** Q2–11, the display half of Q14, Q20–23 and
Q28, with tests. See that PR for per-item status.

## Scope

**In scope:**
- every in-app screen, state and component
- every email
- the chat model's English (`chat/prompts.py`)
- English assembled from data: counts, titles, errors, Telegram replies
- the text Claude and ChatGPT relay from the connector
- accessibility labels

**Excluded:**
- the public landing page (`landing.*`, 302 keys)
- the marketing halves of the weekly, parasha and daily pages: hero, "Why targum", and the
  closing waitlist
- the back office, which is operator-only
- CLI-only text
- all Hebrew, all translations, and generated Hebrew learning content

`/build/<id>` (the `press.*` keys) is **not** the press kit. It is the in-product page where
a reader confirms a build that Claude or ChatGPT set up, so it was audited.

**Legal text** (`legal.html.j2`) was read, but its meaning was not changed. See Q17.

## What changed

- **151 of 2,387 catalogue strings rewritten**, plus about 30 English literals in Python,
  templates and the chat prompt. Everything else was read and left as it was.
- **53 source files** changed. Every change is to wording. One change to how a message is
  put together: a "no text found" error now names the file rather than the server's upload
  path (`pipeline.py`).
- **Two behaviour changes made by audit agents were reverted**, as the brief requires. Both
  are now questions:
  - `press.html.j2`'s `queued` branch (Q2)
  - `add.js` showing the server's refusal (Q3)
- **Test pins** that quoted changed English were updated. No brand test was changed.
- **Russian:** 112 changed keys were re-read against their Russian and stamped
  (`strings/from/ru.json`), because the Russian still says the same thing. 38 were **not**
  stamped: their Russian still carries a claim the English now corrects. They are listed
  below. See Q1.

### What kind of fixes

The biggest category was **claims the code doesn't back**. The rest were missing next steps,
wrong plurals, internal words leaking out, and inconsistent terms.

- **Claims fixed:**
  - "One press and you're on the list" (it takes two)
  - "That link has been used" (it may have timed out)
  - "we can't read scans yet" (we can)
  - "Today is the first" (no day was recorded)
  - "after your second day" (the line needs a second word)
  - "This is this week's" (shown on archived issues too)
  - "press Start on targum" (no such button)
  - "reads at your level" (§6 forbids telling readers their level)
  - "The Terminal has the detail" (shown to hosted readers)
  - "This playlist needs N credits" (only the ticked texts count)
- **Next steps added:** PDF, audio and upload refusals; chat failures; "Nothing here matches
  that"; spent links.
- **Plurals:** seven singular forms said "words".
- **Internal words removed:** build, quote, thread, queue, brought, chunk, "Officialese",
  "register".
- **Terms made consistent across the app:**
  - "Your targums", not "your shelf", in mail and Telegram
  - "Chats", not "Conversations", for the chat list, palette and nav
  - "highlight" for the `m` toggle, and "mark" only for setting a word's level
  - "section" on Learn, as in the reader and Your Progress
  - "Exit full screen" everywhere
  - "Remove {file}" on both upload forms
- **Chat model:** its English rules gain "main point first", "no stock phrases" and
  "explain a newcomer's term the first time". Every rule `test_chat_prompts.py` asserts is
  still said.
- **Emails:** the waitlist-confirm, digest-confirm and invitation copy was corrected, and the
  ready email says "Your targums". The Desktop notes kept by `scripts/mail_notes.py` now
  hold the old wording for those four emails. Run `mail_notes.py push --force` after merging.
  The notes held no unpulled edits when I checked.

## How it was checked

| Method | What |
|---|---|
| **Code** | Every catalogue key, and the English literals in every template, script and user-reachable Python path in scope. Each claim was checked against the code that makes it true or false. |
| **Rendered** | Every email was rendered HTML and text, before and after, with long titles, missing names, each read / listen / watch variant, and the weekly announce. Templated messages were run with 0 / 1 / many counts and long titles. Sign-in and waitlist pages were rendered by the account slice. |
| **UI** (running app, hosted mode, a throwaway test account, 390px and 1280px) | Sign-in with a bogus and a reused link; the waitlist spent link; /you language refusal; /progress empty and with one word; the Playlists empty state; the chat empty state (forced visible); the /connect FAQ; /add translation and transcript pickers with a real upload; /library search; Learn, /texts tabs, and the 404, signed in and out. 54 screenshots. |
| **Could not verify in UI** | The reader page and word card: there was no catalogue locally, and building a text costs a model call. Also: `?signin=expired` (a dead path); the waitlist join submit (it would send mail); the MCP approval page with a real Claude/ChatGPT client; Telegram; actual model replies. These were checked in code only. The chat model's English was reviewed through the prompt and the stored test and eval replies. No new generations were run, since the brief allows no model spend. |
| **Tests** | Every test file was run against the worktree's `src`: 208 files. Everything passes except `test_strings::test_a_translation_is_not_left_behind_when_its_english_changes`, which fails on the 38 unstamped Russian keys and will pass once Q1 is settled. `ruff check`, `ruff format --check` and `mypy` are clean. The private half (`test_private_half.py`) does not exist in a worktree. No private-half module references a changed string key by its English. |

## Layout problems seen (not fixed — not copy)

- **/progress with no words:** the empty-state line is placed after the footer include, so
  it renders **below the footer** and the page body is blank.
- ~~**Sign-in pages at 1280px:** the footer is squeezed into the card column.~~ Fixed in #535.
- **/you at 390px:** the "In Hebrew, targum calls you" choices wrap, so the Hebrew options
  read out of order.
- **/library at 390px:** the Cards/List switch wraps below the sort, leaving its divider
  stranded.
- **The 404 page** offers "Sign in" and "Join the waitlist" to signed-in readers.
- **The /you language refusal** isn't in a live region, so screen readers don't announce it.
- **Telegram:** a quote that starts with a Hebrew title may render right-to-left, with the
  full stop on the wrong side. A long truncated title ends "…." or "?.".
- **Likely to wrap on phones:** the known-line prompt, the ledger tile labels, and "Easier —
  up to 1 word in 5 hard".

## Gaps: English that Russian readers still see in English

- `learn.js` "New: {name}"
- the sign-in page's "link sent" message (the page gets only `signin.*` keys)
- `chips.js` lines sent as the reader's message
- much of the reader's non-catalogue English
- `accounts.py` refusals
- build-time errors (Q6)

These predate the audit. They are listed for a future i18n pass.

## Russian keys left stale (Q1)

Resolved in Pass 2: all 38 rewritten and stamped.

## Coverage by area

Each area below was one audit slice. Status per row:
- **reviewed:** read, fine as it was
- **changed**
- **needs input:** see `COPY_QUESTIONS.md`
- **could not verify**

"How checked" says whether the row was checked in code, rendered, or seen in the running app.
The UI results above apply on top of these.

### Area: Copy audit: learn slice (front door and progress)

Scope: every `learn.*`, `progress.*` and `charts.*` key (244 keys), plus the English literals in
`learn.html.j2`, `index.html.j2`, `progress.html.j2`, `_first_language.html.j2`, `_front_bar.html.j2`,
`_front_join.html.j2`, `_join_form.html.j2`, `learn.js`, `first.js`, `progress.js`, `charts.js` and
`events.js`. Every number and claim was checked against the function that computes it (`charts.js`
`totals / known / reach / common / longest / days / collect / drawGrowth`, `progress.js`
`drawLedger / drawStanding / drawLevel / drawDays / drawSpent / drawReading`, `learn.js`
`stepUp / firstText / drawKnown / drawArrival / offerClaim`, `serve.py _suggest / _totals`).
The rendered checks are the JS harness tests (`test_progress_js`, `test_learn_js`) and the
browser tests (`test_pages_browser`), which run the real assets and read back the drawn text.

19 catalogue strings changed (see `changes/learn.json`). No literal (non-catalogue) English edited.

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Learn: page title, loading line | `learn.page.learn-targum`, `learn.page.opening-your-texts` | code | reviewed | |
| Learn: load failure | `learn.page.we-couldn-t-load-your-texts`, `learn.page.reload-…` | code | reviewed | Says what happened and what to do. The catch also fires on an expired session, where reloading lands on the sign-in door, so the advice still works. |
| Learn: empty shelf (`#nothing`) | `learn.page.nothing-here-yet`, `…find-something-in-the-library`, `learn.page.or`, `…add-your-own` | code | reviewed | Now only a fallback: `learn.js` hides it on every successful load, and a failed load shows `#learn-failed` first. |
| Greeting and today line | `learn.greeting.*`, `learn.this-week` | code | reviewed | Transliterated greetings (Boker tov and the rest) are deliberate (§12, 2026-09-14). |
| Known count on the head row | `learn.known-words.*`, `learn.known-start` | rendered (test_learn_js) | changed | `.one` said "words". In English it is never shown, because the floor is 10, but it is now right. The prompt under the floor is an instruction and is fine. It is long beside the date on a phone: see the layout notes. |
| Arrival, language screen | `TONGUES`, `OTHER_TONGUE` in `learn.js` (not catalogue) | code | reviewed | Shown only to browsers that give a Russian sign (§12, 2026-09-28). |
| Arrival, EN · RU switch | `learn.arrival.switch-russian` (aria) | code | reviewed | |
| Arrival, subjects screen | `learn.arrival.what-are-you-interested-in`, `…pick-three-or-more`, `…pick-more`, the 19 subject labels | rendered (test_learn_js) | changed | The hint was indirect ("what to put in front of you"). It now reads "We'll use them to choose texts for you." That is accurate: interests pick the first text (`firstText`) and the Suggested door (`_suggest`). |
| Arrival, level screen | `learn.arrival.how-much-hebrew`, `…level-hint`, `learn.level.*` | code | reviewed | Wording fixed by §12 (2026-09-19 and 2026-09-28). "We'll adjust as you mark words" is true: `charts.seed` is outvoted once measured. The letters א…ו are not explained here. They are the "smaller half", which is deliberate (see questions). |
| Arrival, connector card | `learn.arrival.connect-asks`, `…connect-hint`, `…connect-every-app`, `learn.arrival.open` | code | reviewed | |
| Arrival, controls and step | `learn.arrival.next`, `…skip`, `…back`, `…step` | code | reviewed | |
| Sheet head: states | `learn.state.*`, `learn.page.continue-reading`, `learn.suggested-for-you`, `learn.from-the-conversation` | code | reviewed | The verb follows the medium (§6). |
| Sheet head: facts line | `learn.scene-of`, `learn.scene`, `learn.words-left.*`, `learn.words.*`, `learn.chapters.*`, `learn.chapters-translated`, `learn.parts.*`, `learn.minutes`, `learn.video`, `learn.audio`, `learn.opened`, `learn.not-opened`, `learn.finished`, `learn.minutes-left`, `learn.minutes-about`, `learn.read-share` | code | reviewed | "parts" here and "sections" on Your Progress and in the reader are the same thing (see Terms). |
| Sheet head: known share | `learn.known-share` | rendered (test_learn_js) | reviewed | "You know 40%" leaves out "of what". I left it because the Suggested door's server reason already says "You know 50% of its words." in the meta line, and the chip repeats it beside that. A longer chip would double the repetition. Flagged below. |
| Sheet hints and Open | `learn.page.read-here-…`, `…listen-here-…`, `…watch-here-…`, `learn.page.open-the-reader` | code | reviewed | |
| Suggested door: reasons | `learn.why.start`, `learn.why.step-up`, `learn.why.about-here` | rendered (test_learn_js) | changed | "Where most people start" claimed something about other people. The code (`stepUp`) just picks the easiest unread text, so it now reads "An easy place to start". `because` from the server belongs to the chat slice. |
| Doors and menus | `learn.recent`, `learn.subscriptions`, `learn.all-your-targums`, `learn.page.all-your-targums`, `learn.page.your-targums`, `learn.finished-mark`, `learn.suggested`, `learn.open` | code | reviewed | The heading `"New: " + name` (learn.js, the landed-instalment sheet) is hard-coded English outside the catalogue, so a Russian page shows English. Flagged. |
| Phone cards | `learn.card.*`, `learn.state.carry-*` | code | reviewed | |
| Connector banner | `learn.connect.*` | code | reviewed | Copy fails silently when the clipboard is refused: no error line. This is behaviour, so it is only flagged. |
| What to work on, first time | `learn.work.once`, `learn.page.all-your-words`, `learn.page.all-your-phrases` | code | reviewed | Said once and counts nothing (§12, "Three moments"). |
| Words you may already know (claim offer) | `learn.claim.*` | code | changed | Now says "tick the ones you know", which matches the grid's checkboxes, and speaks as "we". "library" was lowercase and is now "Library", as everywhere else. |
| Scripture track labels | `learn.track.*` | code | reviewed | |
| First-visit translation question | `_first_language.html.j2`, `first.js` COPY | code | reviewed | The English fallback "Translations in X?" is only reachable for a language other than ru. |
| Your Progress: title, empty page | `progress.page.your-progress-targum`, `progress.page.nothing-yet`, `…open-something-from-the-library` | code | changed | "Nothing yet." did not say why the page was empty. It now reads "Your progress starts with the first word you mark.", followed by the existing link. The page is empty until a word or phrase is kept (`charts.collect`). |
| Ledger (inverted block) | `progress.page.what-you-have-built`, `progress.count.*` | rendered (test_progress_js) | reviewed | Each figure matches `charts.totals`/`longest`. "learned on targum" = known and flagged `learned`. Only the longest run is shown, never the current streak (§12, 2026-09-03). There are 7 figures, though the code comment says "four". Nothing explains the difference between "known" and "learned" (see questions). |
| Hours line | `#hours-line` (account.js) | — | could not verify | Filled by `account.js`, which is outside this slice. |
| Time and words | `progress.spent.*` | rendered (test_progress_js) | changed | The filter group's accessible name was "Which". It is now "What you did". The empty-filter line said "Nothing here yet." and now reads "Nothing recorded for this choice yet." "recording is stopped" matches the account page's "Stop recording". |
| What you knew of what you read | `progress.reading.*` | rendered (test_progress_js, test_pages_browser) | changed | The note's first sentence was a fragment and is now active voice. "So far: 2." is now "Months so far: 2.", which matches the Russian. I checked the fall sentence: it is gated on a drop in tenths. |
| Milestones panel | `progress.page.milestones`, `…counted-from-…`, `progress.mark.*`, `progress.milestone.*` | rendered (test_progress_js) | changed | "Another 38 to 1,000." is now "Another 38 known words to reach 1,000.". The start line said "Mark a word as you go", but the count moves only on known words (`charts.known`), so it now says "as known". |
| Ladder panel (ulpan, CEFR) | `progress.page.ulpan-level`, `charts.ladder.*`, `charts.ulpan.*`, `progress.basis`, `progress.level.*` | rendered (test_progress_js) | changed | The `.one` forms said "words". The start line said "this starts" and now says what starts. Ulpan and CEFR are not explained anywhere a newcomer meets them (see questions). |
| Days on targum | `progress.page.days-reading`, `…every-language-together-…`, `progress.days.*` | rendered (test_progress_js) | changed | "Today is the first." showed when no day was recorded, but opening Your Progress records none (`reader.js` writes the day). It now reads "Open something and today is your first." The aria label drops "yet". Missed days stay the resting colour. |
| Status bar ("Where they are") | `progress.page.where-they-are`, `progress.status.*`, `progress.chart.status`, `progress.empty` | rendered | changed | The heading is now "How well you know them". It sits over the just met … known bar and names what the bar measures. |
| How common chart | `progress.page.how-common-they-are`, `…how-often-…`, `progress.band.*`, `progress.chart.bands`, `progress.empty` | code | needs input | For a language with no frequency bands (Yiddish, Aramaic) this chart says "Nothing marked yet." even when words are marked. That is false, and fixing it needs a new string (see questions). |
| Growth line | `progress.page.words-saved-over-time`, `…from-when-you-first-marked-each`, `charts.growth.*` | code | changed | "after your second day" was wrong: the line draws from two dated saved words, on any days. It now reads "once you've saved a second word". |
| Beta note | `#beta-note` (lang.js) | — | could not verify | Outside this slice. |
| Contents page (`index.html.j2`) | `contents.*` keys | code | reviewed | These keys are not in this slice, so I changed nothing. Flag: "Start reading" is the one primary button even when the text `has_audio`, against §6's read/listen/watch rule (listen/watch, or neutral "Open"). |
| Front bar, join section, join form | `_front_bar.html.j2`, `_front_join.html.j2`, `_join_form.html.j2` | code | reviewed | All `landing.*` keys, excluded by the brief. No literal English beyond "targum". |
| events.js | — | code | reviewed | No user-facing copy. |

#### Layout notes (flagged, not fixed)
- `learn.known-start` ("Open something, tap the words you don't know and talk to targum about any line.")
  sits in the today line beside the date. On a phone it wraps to three or four lines under the greeting.
- On the phone ledger, the tile labels "days in your longest run", "words learned on targum" and
  "targums finished" will wrap to two lines under display-size figures.
- The Suggested door repeats itself. The meta line carries the server's "You know 50% of its words.",
  and the known chip beside it says "You know 50%" (`test_learn_js` pins both).
- The `"New: " + name` sheet heading (learn.js, `landed()`) is English on a Russian page.

#### Terms
- **known / marked known**: the ledger says "words marked known", the milestones "N words known",
  and Learn "You know N Hebrew words". These are consistent in meaning. "known" is the fourth
  status after just met / getting there / nearly there, and the same four words appear in `progress.status.*` and `charts.status.*`.
- **learned on targum**: a known word that was saved below known first. Nothing on the page
  explains how it differs from "known" (see questions).
- **saved / on your list**: the ledger says "words on your list", but the growth chart says "Words saved over time",
  "{total} saved" and "N words saved between…". This is one count under two names. I would pick "saved" or
  "on your list" app-wide. I left it, because "saved" is also the finished box's and the reader's word.
- **section / part / chapter**: Learn's facts say "{n} parts". Your Progress and the reader say
  "section" ("Each section you finish", "mark its section done"). These are the same unit. I recommend "section" on Learn's cards too.
- **level**: "Ulpan level" and "CEFR level" appear only as the ladders' headings, "A guide, not a placement", and in my
  "your level starts here". The ulpan letters are shown on the arrival without any explanation.
- **Library**: capitalised as a place everywhere in this slice (fixed in the claim note).
- **targum / targums**: "targums finished" in the ledger and "All your targums" on Learn are consistent.

### Area: Copy audit — library slice

Scope: every `library.*`, `shelf.*`, `playlists.*`, `lists.*`, `playlist-menu.*`, `series.*`, `set.*`, `vocab.*`, `yours.*`, `follow.*`, `claim.*`, `suggest.*` key (413 in en.json, all read), plus template and JS literals in library / shelf / playlists / set / yours / _yours_tabs / _fold / _chips and the 12 owned assets, plus reader-facing English in `series.py` and `catalogue.py`.

Result: 20 catalogue strings changed (see `changes/library.json`). Two call-site literals edited by hand because the sync tool could not match them: the two-line literal for `set.page.only-this-many-fit` in `serve.py`, and the two model-facing `because` sentences in `chat/tools.py` that `test_chat_tools` requires to equal `suggest.passage` and `suggest.looked-up`. Test pins updated in test_library_js, test_yours_js, test_yours_tabs_browser, test_claim_js, test_follow_js, test_vocab_js, test_quote_set, test_strings and test_chat_tools.

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Library: page title, tabs (All texts / Beit Midrash), search, the filters under "Filters" / "Fewer filters" | `library.page.*`, library.html.j2 | code | changed | Search placeholder: the script replaced the template's "Search titles in Hebrew or English" with "Search a title, Hebrew or English", which read as three things to search. Both now say "Search titles in {language} or English". |
| Library: guidance note above the list (base, per kind, per register, audio/video, sort, "—") | `library.note.*` | code | changed | "Tap one to open it." → "Tap a text to open it." (the line is often the first on the page, so "one" had nothing to refer to). The other notes were reviewed and left alone. |
| Library: fit line ("352 texts · showing [you can read now]") | `library.fit.*`, `library.tally.*` | code | reviewed | |
| Library: subject chips, kind chips, register switch, media/length/hard-words selects | `library.subject.*`, `library.kind.*`, `library.register.*`, `library.spoken.*`, `library.length.*`, `library.level.*` | code | reviewed | "Easier — up to 1 word in 5 hard" is a long select option. It will be cut short in a narrow `<select>` on a phone. |
| Library: cards, the table (column heads, sort buttons, Cards/List) | `library.column.*`, `library.sort.*`, `library.shape.*`, `library.you-know`, `library.known.none`, `library.new`, `library.next`, `library.start-here`, `library.finished` | code | reviewed | |
| Library: Beit Midrash doors and crumbs | `library.door.*`, `library.where.*`, `library.note.doors` | code | changed | "Pick a shelf" → "Pick a section". "Shelf" already means Your targums and the public shelf page. |
| Library: empty (no match) | `library.empty.no-match` | code | changed | Adds the next step: "Try another search or fewer filters." |
| Library: empty language (with and without the reader's own texts) | `library.empty.language*` | code | reviewed | The "Not here? Add your own." link at the foot gives the next step. |
| Library: building a text (progress lines, wait estimates, Start reading / listening / watching, Not now, could not start) | `library.build.*`, `library.wait.*` | code | reviewed | These are shared with the add/press flow. |
| Library: covers (Draw cover / Drawing… / Drawn) | `library.cover.*`, covers.js | code | reviewed | Only appears on deployments that have a key for drawing covers. |
| Your targums: tabs, "What's a targum?" definition and example | `yours.tabs.*`, `yours.defined.*`, _yours_tabs.html.j2 | code | reviewed | |
| Your targums: sifting (status chips, search, order) | `yours.sift.*` | code | changed | Adds a next step to no-match: "Try another search or filter." |
| Your targums: Your uploads empty | `yours.uploads.empty` | code | changed | "Nothing you've brought yet" used the team's word ("brought"). Now: "Nothing you've added yet. What you paste, upload or link on Add is kept here." |
| Your targums: empty account ("Nothing here yet." + Library link) | `yours.page.nothing-here-yet`, `yours.page.find-something-in-the-library` | code | reviewed | |
| Your targums: series folded / inside a series (← All, episode counts) | `yours.series.back`, `shelf.series.count.*` | code | reviewed | |
| Shelf rows: status, length, known share, added/opened, playlists, rung, ⋯ menu, Chapters/Translate, Add to playlist | `shelf.*`, shelf.js | code | reviewed | "You know {share}%" matches the design.md example. |
| Shelf rows: a text being built (Building, % done, waiting behind N) | `shelf.building.*`, `shelf.status.building` | code | reviewed | |
| Shelf: Delete → "{title} is in Trash" + Undo; the Trash panel (Restore, "goes for good…") | `shelf.delete*`, `shelf.binned`, `shelf.undo`, `shelf.put-back`, `shelf.goes-*`, `yours.page.trash`, `yours.page.we-keep-these-for-seven-days` | code | reviewed | "Move to trash" (tooltip) and "Trash" (section) differ in capitals. Minor; left as is. |
| Shelf on Learn: empty, empty language, See all | `shelf.empty*`, `shelf.see-all` | code | reviewed | "We'll keep the texts you open here" is accurate: yours.js adds shared texts once they are opened. |
| Public shared shelf page (/shelf): Sign in, empty | `shelf.page.*`, shelf.html.j2 | code | reviewed | The shelf name and blurb are content. |
| Playlists page: signed out, add sheet (?add=), New playlist + Confirm | `playlists.page.*`, playlists.html.j2 | code | reviewed | The owner chose "Confirm" on 2026-09-24 (#415). |
| Playlists page: empty | `playlists.page.none-yet` | code | changed | "Add a text from its ⋯ menu" was wrong on Your targums, where Add to playlist is a button on each row. Now: "Use Add to playlist on any text to start one." |
| Playlists page: From targum | `playlists.page.from-targum*` | code | needs input | "Free to open" is the owner's wording (#415), but design.md §6 bans price words inside the product. See questions. |
| Playlists page: each playlist (count, Start, Rename, Save, Delete → Confirm delete, move up/down, Remove, Getting ready, could not) | `playlists.*` | code | reviewed | A11y gap: "Start" and "Rename" have no accessible name that includes the playlist's name (Delete has one). With several playlists, a screen reader hears the same "Start, Rename" for each. |
| Playlists: errors (unreached, failed, gone) | `playlists.unreached/failed/gone` | code | reviewed | |
| Add-to-playlist menu (in place, from a shelf row or the reader's ⋯) | `playlist-menu.*` | code | changed | "Couldn't add it" / "Couldn't load your playlists" → "We couldn't…" (design.md §6: we own the error). |
| Set page /set/<id>: ticked list, credits per text and in all, Confirm, the aside | `set.page.*`, set.html.j2 | code | reviewed | Credits are never explained on this page (1 credit = 1 minute). The page is reached from outside the app (connector), so this reader may not know the term. Flagged, not changed. |
| Set page: refused (not enough credits) | `set.page.only-this-many-fit` (serve.py) | code | changed | {total} counts the ticked texts still to be made, not the whole playlist. "This playlist needs" → "These texts need". |
| Set page: preparing / ready / nothing can be added / Check progress / Start | `set.page.*` | code | reviewed | |
| Series list (Follow switch, Open, no instalment) | `follow.*`, follow.js, `series.*.name/what` (series.py via said_in) | code | changed | "Nothing this week yet." also appeared under daily series. Now: "The latest one isn't ready yet." A11y gap: the switch's name is only "Follow" / "Following". It has no series name and changes with its state. |
| Series stop page (from an email link) | `series.stop.*` | code | changed | The h1 was lowercase "your subscriptions". It is now "Your subscriptions", as in the nav. Gap: the page never names the series being stopped ("when a new one comes out"), and its `<title>` is the Weekly News Digest's (builder.weekly_note, mail slice). |
| Your Words: table, filter, search, export (CSV / Anki), translations-in, empty states | `yours.page.*`, `lists.*`, `lists.csv.*` | code | changed | Adds a next step to no-match: "Try another word or filter." The other empty states were reviewed. |
| Your Words: What to work on (I know this / Still learning / Practise these… / Show others) | `lists.work.*` | code | reviewed | `lists.work.line` / `phrase-line` are sent to the chat as the reader's own words. They are fine. |
| Word / phrase card on the lists | `lists.card.*` | code | reviewed | |
| Words you may already know (claim grid) | `claim.*`, `yours.page.words-you-may-already-know` | code | changed | "We've marked 2 as known." → "We've marked 2 words as known." |
| Stage scale, legend, own-meaning field, copy button | `vocab.*` | code | changed | The fallback placeholder "Enter text" → "Your own meaning", matching the field's aria-label and every other caller. |
| Your Phrases | `yours.page.your-phrases`, `yours.page.phrases-*`, `lines-corrected-in-conversation` | code | reviewed | |
| "Something to read" suggestion card (chat) | `suggest.*` (chat/tools.py because_in) | code | changed | Removed "reads at your level" (design.md §12 says never tell the reader they are at a level). Replaced "A learner looks up N%", which is not what the number measures, with the Library's own definition of hard words. |
| Chat chips lines | chips.js `LINES` (not catalogued) | code | reviewed | These are the reader's own words to the model, and chip labels come from `/chat/list`. There is no Russian for LINES, but they are what the reader "says", so that is probably intended. |
| _fold.html.j2 | template | code | reviewed | No English. |
| _chips.html.j2 | `chat.page.things-to-ask` | code | reviewed | The key belongs to the chat slice. |
| list.js (playlist foot in the reader) | `reader.list.*`, `reader.finish.*` | code | could not verify | These keys are the reader slice's, so I did not change them. Noted: "You met 1 word, 0 of them new." is possible. The reader's menu says "Add to a playlist" where rows say "Add to playlist". |
| catalogue.py | — | code | reviewed | No reader-facing English. It has one stderr operator message and image-model prompts. Kind, register and collection names reach readers through `library.*` keys and catalogue content. |
| series.py | series names / blurbs | code | reviewed | The English defaults mirror the `series.*` keys. The series blurbs use Jewish study terms (mishnayot, tractates, sedarim, Masoretes) aimed at the people who follow them, so I left them. |
| Unused keys | `shelf.not-opened`, `shelf.chapters.*`, `shelf.parts.*`, `yours.page.text/chapters/last-opened/export/lines-you-rewrote` | code | reviewed | No call site found. These keys are dead. |

Rendered / UI checks: none. Every row above was checked against code and strings only.

Layout flags (not fixed): the long level options in the Library's Hard words select; `yours.defined.body` is three lines on a phone (by design); Library notes joined with " · " can reach two long clauses on a phone; the refusal "These texts need {total} credits and you have {n} left. Untick some and try again." sits in the set page's narrow card, so expect three lines.

#### Terms

- **Library**: everyone's catalogue (nav "Library", "the library" in running text). Tabs: **All texts**, **Beit Midrash**. A door inside the Beit Midrash is now a **section** (it was "shelf" in one note).
- **Your targums**: everything of the reader's (nav, page h1, tab strip). Tabs: **All targums**, **Your uploads**, **Playlists**. A **targum** is defined on the page as a text with its translation held line by line. The search says "Search your targums".
- **text**: one item, in the Library ("{n} texts", column "Text") and inside playlists ("{n} texts"). Your targums calls the same thing a targum, so both words name one object. That follows design.md §12 (2026-09-26); I report it rather than propose a change.
- **shelf**: never a visible label inside the product any more, except as a URL/page for the public shared shelf (/shelf). Leftover key names (`set.page.on-your-shelf`) now say "Already yours".
- **Your uploads** (tab) vs **Add** (page): the empty state now uses "added" and names Add. "brought" no longer reaches the reader.
- **playlist**: "Your playlists", "New playlist", "Add to playlist" (row button and menu). The reader's ⋯ menu says "Add to a playlist" (`reader.page.add-to-playlist`, reader slice). That is an inconsistency, and I report it rather than fix it.
- **Your Words** / **Your Phrases** in title case (design.md uses "Your Words" too) vs **Your targums** / **Your playlists** / **Your subscriptions** in sentence case. Your Progress in the nav is also title case. This is an inconsistency in casing across the app, and I report it rather than fix it.
- **word list**: the Your Words page. The claim grid calls it "your list" ("not on your list yet").
- **Known / Still learning / 1 just met · 2 getting there · 3 nearly there / Ignored**: the stages, the same across vocab.js, the Your Words filter and What to work on. The stage-4 tooltip for ignore reads "A name or a number".
- **Hard words**: the Library's measure, defined as "rare in everyday use". The suggestion card now uses the same definition. The model-facing `because` literal in chat/tools.py was changed to match, because test_chat_tools requires it.
- **credits**: set page and refusal. Never explained there (see above). "Free to open" on From targum is the one price word (see questions).
- **series / Follow / Following / Your subscriptions**: the list says Follow, the nav and the stop page say Your subscriptions, and the emails say "you follow {name}". "Subscription" and "follow" are two words for one act. That is established usage, and I report it.
- **Trash / Restore / goes for good**: consistent.

### Area: Copy audit — reader slice

446 catalogue keys (reader.* 398, contents.* 19, video.* 8, pdf.* 5, pictures.* 4, recording.* 4, speak/stage/note/episode 2 each) plus ~60 literal English strings in reader.html.j2, text.html.j2, print.html.j2, reader.js, contents.js, scenes.js, speak.js, talk.js, words.css/reader.css (the CSS carries no English content strings). 18 catalogue strings changed, 4 literal strings changed, 7 more proposed but not applied (their English lives in Python files outside this slice; see questions/reader.md).

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Bar: mark, title, known share | reader.html.j2 head; reader.page.your-learn-page, targum-learn, reader.header.* | code | reviewed | |
| Bar: reading modes (parallel / interlinear / source) + announcements | reader.page.parallel…source-only, reader.mode.parallel/interlinear/source-only/pages/scroll | code | reviewed | |
| Bar: vowel points / stress marks / chanting marks toggles + announcements | reader.page.vowel-points*, stress-marks*, chanting-marks*, reader.form.* | code | reviewed | The "about 90% right" titles are long tooltips, fine. |
| Bar: highlight-unlearned toggle (m) + announcements | reader.page.highlight-*, reader.mode.marking/not-marking, reader.page.mark-words-as-you-read | code | changed | Key list and announcements said "marking"; the button says "highlight". Now "highlight" throughout; "mark" stays for setting a level. |
| Bar: case lens | reader.page.show-one-case*, one-case-at-a-time, reader.case.* | code | reviewed | `<option>` case names are literal English, not catalogued. |
| Bar: type size, line spacing, full screen | reader.page.*type*, line-spacing, full-screen*, reader.screen.* | code | reviewed | |
| Bar: levels (same news, other level) | reader.page.level, contents.page.written-for | code | reviewed | |
| Bar: renderings / translation switch | reader.page.translation | code | reviewed | |
| Bar: shnayim mikra switch + practice foot | reader.page.shnayim-mikra/read/read-as-usual/by-verse, reader.practice.* | code | reviewed | "By {portion}" and its title are literal English. |
| Phone ⋯ menu row labels (data-what) | reader.html.j2 | code | changed | "Where it lives" -> "The original". All data-what labels are uncatalogued English. |
| Add to playlist | reader.page.add-to-playlist | code | reviewed | |
| Hear a silent section (voice offer): offer, cost, progress, errors | reader.page.no-recording, hear-this-section, voice-costs-credits; reader.js voice block | code | changed | "We're reading this section aloud" -> "We're recording this section now" (it makes a recording; the minutes are its length). Messages are uncatalogued. |
| Talk to targum button + drawer | reader.page.talk-to-targum* | code | reviewed | Term: see Terms. |
| Keys card (keyboard shortcuts) | reader.page.keys, keyboard-shortcuts*, forward-through…, take-back…, close-this-then…, keys-on-the-track, keys-on-the-picture, next-page-pageup…, the-level-on-a-word-s-card | code | changed | Four lines rewritten: the arrows line, u, Esc ("the queue" was internal jargon), the track keys. The "hard" row is an explanation, not a key; left. The Space line and the n line are literal English. |
| First-time line + first-keys line | reader.page.tap-a-word-to-say-how-well, reader.first.keys, reader.first.listen/watch | code | reviewed | |
| Taught-the-tap line on the first card | reader.taught.tap-any-word | code | reviewed | Claim (the tap puts the word on the list) matches the code comments at reader.js ~4634. |
| Word card (gloss): meaning, look-up states, own meaning, root/family, aspect, stress, inferred | reader.card.* | code | changed | "The table" -> "All its forms"; "conjugations" -> "conjugations on Pealim" (it is an outbound link in a new tab). "nothing saved" (disabled look-up when asking is off) left, but it is vague. |
| Word card: grammar labels | reader.grammar.*, reader.tense.*, reader.feature.*, reader.built.* | code | reviewed | Linguistic labels; consistent. |
| Word card: level scale | reader.level.*, reader.grammar.status-* | code | reviewed | |
| Word card: Ask (two turns) | reader.ask.* | code | changed | Placeholder "One more" -> "One more question". |
| Word card: "This meaning is wrong" proposal | reader.card.meaning-wrong/what-it-means/send-correction/correction-taken/correction-lost | code | changed | "Thanks. We'll check it before it changes for anyone." (proposal settled by an editor — claim checked). Gap: a network failure re-enables Send and says nothing (reader.js ~4766); behaviour, not changed. |
| Phrase pick card | reader.pick.* | code | changed | "the sentence is in parallel" assumed a mode name and is wrong in interlinear/source-only; now "the line's translation has the whole sentence". "Remove"/"Keep" actions are literal English. |
| Saved list (words/phrases), empty states, export, Anki | reader.page.words/phrases/export/anki-deck/hide-the-list/drag-across…/tap-or-click…, reader.list.*, reader.export.* | code | reviewed | Empty states say how to start. |
| Bulk mark / undo announcements | reader.rest.* | code | changed | .one forms said "{n} words" (announced "1 words"). |
| Foot: Done / Next / Finish, with and without marking | reader.foot.*, reader.page.done | code | reviewed | "Finish, and mark 12 words known" is the longest button; wraps on a 320px phone. |
| Finished box, Undo, arrival line | reader.finish.*, reader.arrived.* | code | changed | "your progress page" -> "Your Progress", the page's own name. |
| Up next / suggestion / Something else / known-ahead / connector line | reader.next.*, reader.page.read-next, something-else | code | changed | Connector line gets a comma ("…you marked, in Claude or ChatGPT") — without it, it read as words marked in Claude. Wording otherwise as recorded in §12. |
| Playlist mode: where, next, end of playlist | reader.list.label/where/back/next/done/up-next/getting-ready/end-*/your-playlists/back-link | code | reviewed | |
| Pager / paged mode | reader.page.previous-page/next-page/of/said | code | reviewed | |
| Waiting chapter (not translated / not transcribed) | reader.html.j2 waiting-note; reader.chapter.* | code | reviewed | Note and buttons are literal English. The button spends with no cost beside it. |
| Player strip: play, track, step, speed, hear first, save, close | reader.page.position/step/back/forward/speed/slower/faster/hear-first/download-the-audio/close-the-player/save-the-audio/the-recording; reader.js | code | changed | Errors: "…in this browser. Try another browser."; "Allow sound for this site in the address bar, then try again." (was "Check the address bar"). Step labels, hear-first announcements are literal English. "Hear first" has no title explaining it (the announcement does). |
| Video panel: move, corner, transcript/full screen, close, resize | reader.page.*video*, move, transcript, put-the-picture…, play-or-pause…; reader.js SAID_CORNER etc. | code | reviewed | Corner announcements ("Bottom, reading end.") are terse; left. |
| Post head (Instagram/X) | reader.post.* | code | reviewed | |
| Credits foot | reader.page.credits, dictionary-forms-by, vowel-points-by, aspect-partners…, our-dictionary-forms… | code | reviewed | The biblical caveat uses "analyser", "waw-consecutive", "pausal": jargon, but its readers are the ones who know it. |
| Contents page (index): start, rows, portion link, prepare all, per-chapter Translate/Transcribe | contents.* ; contents.js | code | changed / needs input | contents.could-not "do that" -> "start that", matching reader.chapter.could-not-start. "Start reading" on a listen/watch text: see questions. "Prepare all" spends with no cost shown. |
| Public text page | text.html.j2 (text.page.* keys belong to another slice) | code | reviewed | Only literal: "Translation(s)". |
| Print edition | print.html.j2 | code | reviewed | Only chrome is "Words" (lists.* key, other slice). |
| scenes.js / speak.js / talk.js | speak.*, stage.* | code | reviewed | speak.no-microphone has its next step. |
| Import refusals: PDF, pictures, video, recording, Spotify | pdf.*, pictures.*, video.*, recording.*, episode.* | code | needs input | English is shown from the Python literal, not en.json; changes proposed, not applied — questions/reader.md. |
| Weekly note door | note.* | code | reviewed | |

**Material gaps**
- A good share of the reader's English is not in the catalogue, so a Russian reader meets it in English: the phone menu row labels, "By {portion}", the waiting note and its buttons, "Listen to / Play … and follow along / Watch the video", the case options, "Read by", the Space and n key lines, step and video-mode labels, hear-first and corner announcements, player and voice errors, the pick card's Remove/Keep, the grab handle's "Close" and the "Hear" title. Fixing it means new keys, which is outside this audit's tools.
- Nothing was checked in a rendered page or running app; all of it was checked by reading the code. The reader browser suite (336 tests) passes after the changes.

**Layout flags (seen in the code, not fixed)**
- Foot button "Finish, and mark {n} words known" and "Done, and mark {n} words known" wrap to two lines under ~360px.
- The voice offer row (label + button + "This uses about {n} credits" + status) is dense on a phone; it has its own row, but the status line "Thanks. We're recording this section now. It runs about N minutes." is long beside it.
- The keys card's arrows line is long in one `<dd>`; fine on a desk, the card is hidden on touch.
- "conjugations on Pealim" is a little longer in the card's grammar line.

#### Terms
- **Mark / marking** — setting a level on a word (just met, getting there, nearly there, known, ignored). **Highlight** — the m toggle that tints unlearned words. These two had drifted together ("Marking words as you go" for the highlight); now separated.
- **Keep / saved / kept** — mixed: "What you have kept from this text", "to keep:", "Keep" (phrase), vs "your saved words", "nothing saved". Not changed; the app should choose one (suggest "saved").
- **Take back / Undo** — the Undo button, but announcements say "Taken back." / "Took back {n} words." and the key list "take back the last level". Consistent within the reader; different word from the button.
- **Done / Finish / Finished** — Done at the foot of a section, Finish as the last press of a playlist, "Finished" in the box. Deliberate (§12 "The foot is one block").
- **Talk to targum vs chat** — the reader's button and drawer say "Talk to targum"; the card's Ask says "Continue in chat"; §12 (2026-09-22) says "the word is chat". The pill name "Talk to targum" is app-wide (nav.talk-to-targum), so not changed here.
- **Your Progress** — the page's title (you.page.your-progress, palette.progress); nav says "Progress"; landing says "Your progress" (lowercase p). Reader now says "Your Progress".
- **Recording / audio / voice** — "The recording", "Save the audio", "Download the audio", "Hear this section", "No recording". Save vs Download for the same file in two places (menu vs strip).
- **Transcript** — used for the video's text view; the contents page says "Transcribe".
- **Credits** — "This uses about {n} credits" is the only cost said in the reader; the chapter Translate/Transcribe and Prepare all buttons spend without one.

### Area: Copy audit — slice `add` (bringing something in and building it)

Scope reviewed: every `add.*`, `bring.*`, `building.*`, `job.*`, `fetch.*`, `file.*`, `upload.*`,
`serve.*`, `x.*` key (308), plus `holding.*` (6) because `holding.html.j2` is in this slice, the
four `chat.page.*` labels `_composer.html.j2` draws (reviewed only; the chat slice owns them), and
the unowned-by-prefix refusals the upload path raises (`pdf.*`, `pictures.*`, `recording.*`,
`video.*`, `episode.*`: 20 keys, reviewed and reported only). Non-catalogue English: `serve.py`
(JSON errors, the stale-tab page, build-failure text, `TargumError`s on the upload and prepare
path), `pipeline.py`, `ingest/**`, `errors.py`, `preflight.py`.

Totals: ~370 catalogue strings and ~45 non-catalogue messages reviewed. 27 catalogue keys changed
(`changes/add.json`), 9 non-catalogue messages changed, plus one display bug fixed in `add.js`.

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Add page chrome: title, h1, "It may already be in the Library", box label, placeholder, the line under it | `add.page.*`, `add.given.*`, `add.html.j2` | code | reviewed | "Library" is capitalised in this link and lowercase ("the library") in every other line on the page. See Terms. |
| Box understanding line, per thing brought (link, few words, description, foreign script, English, each file kind) | `add.thanks.*`, `add.few*`, `add.description*`, `add.foreign.*`, `add.words.*`, `add.photos.*` | code | reviewed | `add.description`, `add.description.talks` and `add.continue.describe` are never used (orphans). |
| Recording: transcript line | `add.spoken.*` | code | changed | `add.spoken.ours` tied credits to "writing it down". But `Library.claim` charges `job.seconds` for any audio, with or without a transcript, so the other case read as free. Now "We'll write down what's said, part by part." |
| Summary line + Change panel (languages, translation, transcript) | `add.summary.*`, `add.how.*`, `add.page.*` | code | changed | "Something else" → "Remove file" (it clears the file). "Plain text or markdown…" → "A text file or an ebook, in reading order" (the field also takes .epub, and "markdown" is jargon). "SRT or VTT, timings kept" → "A subtitle file (SRT or VTT)". |
| Several files paired / left unpaired | `add.unpaired.*`, `add.role.*`, `add.remove` | code | reviewed | |
| Library already has it (typing) / catalogue has a published translation (after Continue) | `add.already.*`, `add.instead.*`, `add.open-it`, `add.translate-anyway` | code | reviewed | |
| Waiting for a price | `add.fetching`, `add.still-working`, `add.uploading` | code | changed | "We're fetching it…" showed for uploads and pasted text too. Now "We're reading it…". The 12-second line claimed every slow wait was a first-in-a-language setup. Now "A long text, or the first in a new language, takes us longer." |
| Link described before price ("What targum found") | `add.found.*` | code + browser test | changed | "What targum found" → "What we found" (§6 "we"; the search list already said it). "You know {n} words in ten" now matches the quote card's "You know about {n} words in 10". |
| Cost card (Add): title · facts · first lines · doubtful lines · wait · press | `add.job.*`, `add.doubtful.*`, `bring.wait.*`, `add.start-reading` | code | needs input | The card says only the wait. It never says credits, though /press and Telegram say "Uses N credits" (Q1). The press is "Open" (§6, #337) and it spends (Q2). |
| Wait estimates | `bring.wait.*` | code | reviewed | Verified. Taken from the box's own history (`job.usually`) where there is one, else from formulas. The first part or chapter only, as the copy says. |
| Quote card in chat (model's quote or + file) | `bring.js` `quoteCard`, `bring.*` | code | changed | "{n} minutes of audio"/"{n} hours of audio" read "1 minutes"/"1 hours" at exactly 1 (not pluralised). Now "{n} min / {n} h of audio" (the §12 "6 h 50 m" style). "It'll appear above when it's done" → "You'll find it in Your targums" (a build is a row there from the start, per yours.js reading /jobs). "Do not bring {file}" → "Remove {file}" (same × as on Add). "Audio can be added in the reader" made active. |
| Instagram / TikTok / X post pasted; "Also read the pictures" | `job.*-unavailable`, `job.post-only-pictures`, `job.x-*`, `x.*`, `add.read-pictures.*` | code | needs input | The button says "Also read the {n} pictures" even where nothing else was read: a scanned PDF (where they are pages) and a post whose words are all in its pictures (Q5). |
| Bring a post (form) and its refusals | `add.page.post-*`, `add.post.*`, `serve.post-*` | code | changed | "Paste it into the box above": the form hides the box, so this is now "Press Back and paste it into the box instead." "A post's media is its pictures, or one video" is now the instruction "Add either its pictures or a single video." |
| Credits line on Add; nearly-out warning in the bell | `add.credits.*`, `building.credits.*`, `building.hours.*` | code | changed | "They reset on" → "They come back on" (every other credits line). "See" → "See usage". |
| Building progress in the bell (queued, next, working %, stage words, ready, failed, blocked) | `building.*` | code | changed | Fallback failure now has a next step ("Try adding it again."). |
| Building progress on Add (bar and stage words) | `add.getting-ready*`, `bring.build.*` | code | reviewed | Pipeline messages are mapped to reader words. Unknown ones fall back to "We're getting it ready…". |
| Email me when ready | `building.promise`, `serve.py` `_watch_job`, `Library.tell` | code | reviewed | Verified. Shown only when the server says `watching` (hosted, signed in, mailer present). The mail goes only on success, so "when it's ready" is accurate. Unasked mail after 3 min (`LONG_BUILD_MS`) matches `mail.ready.why`. |
| Out of credits / daily rails / too long / all we can take / no key | `job.out-of.*`, `job.too-long`, `job.all-we-can-take`, `job.no-key` | code | changed | Verified that "Text uploads still work" is true: only audio passes `length` to the monthly sum. "conversation" → "chat"/"chatting" (§12, "The word is chat"). "Try again in 24 hours" is a rolling window (`_since`), so it is accurate as an upper bound. |
| Video / recording limits | `job.video-too-long`, `job.live-stream`, `recording.*` | code | changed | `job.video-too-long` now says the same thing as `recording.video-too-long`, with a next step. `recording.silent-video` says "transcribe", where the rest of the product says "write down what's said" (not mine; reported). |
| Link fetch refusals | `fetch.*`, `job.unreadable.*`, `ingest/url.py` | code | needs input | `fetch.would-not-open` / `fetch.no-such-site` show their raw technical hint to readers: "HTTP 403", "a bot check, not a page", a curl exception, or "More than N redirects" (Q4). The rest are fine. |
| Upload door refusals (size, kind, quota, protected, damaged, parts) | `serve.*`, `upload.protected` | code | changed | "That chunk is too big" → "Part of the upload was too big. Send it again." |
| **Upload refusals on the Add page (display bug)** | `add.js` Continue's `.catch` | code + browser tests | changed | Every sentence the chunked door refused with was replaced by "We couldn't reach targum. Check your connection" (picture over 20 MB, protected file, over quota, and so on). The catch now shows the server's sentence when it has one, as the post form already did. |
| Language refusals at /prepare | `serve.not-in-profile`, `serve.we-translate-into`, `serve.we-can-read` | code | changed | "Add it there" did not say where. Now "…isn't in Your languages yet. Add it in Your profile, then try again." |
| Build lost on restart | `serve.we-lost-that-build-when-we*` | code | reviewed | |
| Build failed with an unexpected error | `serve.py` `_blame` callers (5×), non-catalogue | code | changed | "…The Terminal has the detail." reached hosted readers in the bell. Now "Something went wrong on our side, and we've noted it. Try again later." `incidents.record` writes it down on every path. |
| Build failed with a TargumError | `serve.py` `_blame(error.message)` | code | needs input | Always in English, and any hint is dropped (Q7). |
| No text found in a source | `pipeline.py` segment | code | changed | "We couldn't find any text in {self.source}" showed the server's upload path. It now names the file's own name, or the link. |
| No speech heard in a recording | `pipeline.py` | code | changed | Added a next step: "Check that it's the recording you meant." |
| EPUB / subtitle file unreadable | `ingest/epub.py`, `ingest/subtitles.py` | code | changed | "Could not read the EPUB: x" plus a raw zipfile error → "We couldn't open x. It may be damaged, or not an EPUB." "This EPUB names no package document." → "We couldn't read this book. It may be damaged." "No subtitles found in x" → "We couldn't find any subtitles in x." |
| Small-file door: unreadable kind; empty source | `serve.py` `_written`, `_source_from` | code | changed | Dropped "markdown" and "a Gutenberg or Wikisource id" (jargon): "Paste a link or drop a file." |
| Pictures / PDF pages limits | `serve.py` `_gathered`, `_upload_end`, `pdf.*`, `pictures.*` | code | reviewed | English-only f-strings with no key ("That's N pictures. We can read up to 30 at a time."). Russian readers get English. |
| YouTube with no yt-dlp; read-aloud or transcribe with no key | `serve.py` `_prepare_video`, `serve.cannot-*` | code | needs input | The operator's hint ("install yt-dlp…", "set OPENAI_API_KEY in .env…") is interpolated into reader text (Q6). |
| Description search on Add (Continue with a sentence) | `add.looking.*`, `add.description.look` | code | needs input | It says a look is "off your credits", then shows "Looking used 0:07 of your credits" as a clock. This conflicts with §12 2026-09-24, "chatting is included" (Q3). |
| Chat-side JSON errors owned by prefix (`serve.say-something-first`, too long, mic, voice, sign-in, playlists, prompts) | `serve.*` | code | changed | "too long for one turn" → "one message". The others were reviewed and are fine. |
| Stale-tab page (local run) | `serve.py` `STALE` | code | changed | "This tab has gone stale" → "This tab is out of date". |
| Not-found page / Coming soon | `holding.html.j2`, `holding.*` | code | reviewed | |
| Composer (+, Speak, Send, field) | `_composer.html.j2`, `chat.page.*` | code | reviewed | The chat slice owns these. |
| JSON machine errors ("not found", "bad request", OAuth codes) | `serve.py` | code | reviewed | Not shown on the Add path except `/job/<id>`, which has its own sentence. |
| CLI and operator only (out of scope) | `preflight.py`, `errors.py` (no text), `pipeline.py` ffmpeg / `--pictures` / "Nothing to render", `ingest/fetch/*` (gutenberg, sefaria, published, weekly ids), `file.*` keys, "Port in use" | code | reviewed | Not reachable by a reader through the web app. Not edited. |

#### Layout flags (not fixed)
- The Add button row can hold five controls: Choose files, Record, Bring a post, Ask targum and Continue. It will wrap to two or three rows on a phone.
- `job.out-of.credits` is four sentences. It sits in the card's `.cost` span beside a title and facts, which is long on a phone.
- In the bell, a failure reads "{title}: {sentence}". A Hebrew title, then a colon, then an English capitalised sentence sits right to left then left to right on one line. It is isolated (U+2068), so it will not reorder, but it is long.

#### Terms
- **credits** for the allowance, "a credit is a minute". This is consistent in the slice, except for the look's clock-as-credits line (Q3).
- **Your targums** is where a build lives. "the shelf" appears only in mail (`mail.ready.lead`: "It's on your shelf now.") and in code. Mail says shelf and the app says Your targums: inconsistent (mail slice).
- **library / Library**: lowercase in sentences, capitalised in the Add page link "It may already be in the Library." Not uniform. The nav says "Library".
- **chat vs conversation**: the slice now says chat or chatting in refusals. `add.few.talks`, `add.description.look` and `add.looking.*` still say "turn of conversation" (Q3 covers them). `chat.uploading` and others belong to the chat slice.
- **photo / picture / page**: "photos of pages" on the box, "pictures" in refusals and on the Also-read button, "pages" for a PDF scan. Mixed. Picture is the §12 word.
- **write down what's said / transcribe**: "write down" is the reader's word. "transcribe" survives in `recording.silent-video` and "we transcribe" in the summary line (`add.summary.we-transcribe`, lowercase, in the summary grammar).
- **Open** is the neutral press (§6). It is also the press that spends (Q2).
- **"The library is always free"**: "free" is a price word in a product with no prices (§6). It is widely used and settled. Flagged only.

### Area: Copy audit — chat slice (in-app chat, Telegram, the chat model's English)

Reviewed: all 87 `chat.*` / `telegram.*` keys, `job.out-of.chat`, `speak.*` (2), the 8
`you.telegram.*` keys (read only, account slice), the quote-card keys the chat draws
(`bring.*`, read only), `SYSTEM` + `ledger()` + `shut_hosts()` in `chat/prompts.py`, and the
English assembled in `chat/session.py`, `record.py`, `transcript.py`, `check.py`,
`telegram.py`. 13 catalogue strings changed, 4 non-catalogue edits (prompt ×3, model note ×1).

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Page title, list head (New, Conversations) | `chat.page.conversations*`, `chat.page.new` | code | needs input | "Conversations" vs the house word "chat": see questions. "New" left alone (two words beside it would mix terms). |
| Empty chat (no conversations) | `chat.page.ask-us-for-something-to-read-or` | code + test_pages | changed | Said "we answer from the library and your own shelf"; web search is on by default, so now "We look on your shelf, in the library and on the web." |
| Chips (empty state) | `chat.chip.*`, `chips.js` LINES | code | reviewed | The lines chips.js *says* ("Use my new words in a short conversation." etc.) are English literals, untranslated for Russian readers: flagged, not mine to change. |
| First exchange (word checklist card) | `chat.claim.ask`, `chat.claim.done` | code | reviewed | "Your words and phrases, in your account" checked: it is the account panel link (`nav.your-words-and-phrases`). |
| Suggestion turn ("Find me something to read") | `session.py` SUGGEST_*, `suggest.*` reason, `chat.another` | code + rendered | reviewed | Renders "Here's something to read. You know 82% of its words." above a card that says "You know about 8 words in 10 here": two forms of one number in one turn (flag; `suggest.*` is not this slice). |
| Suggestion errors | `chat.suggest.out`, `chat.suggest.cannot` | code | changed | `.cannot` had no next step → "We can't get that one ready right now. Ask us for something else." |
| Composer (placeholder, Speak, Send, +, Your message) | `chat.page.*`, `chat.write-in`, `_composer.html.j2` | code | reviewed | |
| Speak / microphone | `speak.*`, `chat.page.speak` | code | reviewed | |
| Reading drawer row | `chat.page.reading`, `chat.page.explain-this-sentence`, `chat.talk-about-it`, `chat.ask.*` | code | reviewed | "Let's talk about it" is 4 words on a button; it is David's own phrase in §12 (2026-09-11), kept. Likely to wrap beside a long title on a phone. |
| Thread: pair / translations toggle / word popover | `chat.hide-translations`, `chat.page.show-translations`, `chat.look-up`, `chat.looking`, `chat.not-found`, `chat.the-translation`, `chat.why-corrected` | code | reviewed | |
| Thread: doors | `chat.open-text`, `chat.open-set` | code | reviewed | `{name}` is the folder slug with hyphens as spaces, lowercase; readable. |
| Working state (tool in progress) | `chat.doing.*` | code + test_chat_js | reviewed | |
| Upload from the + | `chat.uploading*`, `chat.could-not-send`, `chat.still-answering` | code | reviewed | |
| Card that asks the reader to press (in chat) | `bring.js` quoteCard: `bring.read-this`, `bring.started`, `bring.cannot`, `bring.known.*`, `add.job.*` | code + test_chat_js | could not verify (not my keys) | Read only. Another slice changed `bring.started` during this run. Button "Open this" is the product's press word; press page still says "Read this" (`press.page.read-this`), see Terms. |
| Conversation foot | `chat.foot.*`, `chat.save`, `learn.minutes` | code + test_chat_js (rendered) | changed | "none marked yet" → "none marked as known yet" (a newcomer doesn't know what is marked). Zero case renders "0 words you have not met": acceptable, noted. "Save as targum": see questions. |
| Conversation list rows, More, ago | `chat.more`, `shelf.ago.*`, `palette.untitled` | code | reviewed | A row with no title says "Untitled" (palette key). |
| Error: model unavailable (no key) | `chat.cannot-answer` | code | changed | "Everything you have still opens" → "Your texts and the library still open." |
| Error: network / server unreachable | `chat.unreached` | code | changed | Adds the useful next step: "Check your connection and try again." |
| Error: turn failed | `chat.could-not-carry-on` (session.py ×2) | code + test_chat_session | changed | → "We couldn't answer that. Try again." (pins updated). |
| Error: turn too long | `chat.too-long`, `TURN_TOO_LONG` | code | reviewed | |
| Error: over the daily rail | `job.out-of.chat` (serve.py) | code | needs input | Text fine; "The library is always free" is price language inside the product (§6). Shared with 3 other `job.out-of.*` keys, so left for one decision: see questions. `{hours}` is always 24, no plural risk. |
| Error: monthly credits reached by talking | `job.out-of.talk-credits` | code | reviewed | Not my key; same "always free" point. |
| Model's English: voice rules | `chat/prompts.py` SYSTEM | code + test_chat_prompts | changed | Added: main point first, one idea a sentence, no stock phrases ("Great question", "I'd be happy to", "dive in", "unlock"); explain a newcomer's term (binyan, niqqud, ktiv male) the first time. All asserted rules kept; no new "English"/"!"/"Targum". |
| Model's English: the card | SYSTEM quote paragraph | code | changed | Example line "Your card is here. Press it and we'll get the text ready" → "Press the button on the card and we'll get it ready" (plainer; says what to press). Hebrew contract's "do not tell them to press it" untouched. |
| Model's English: brought file waiting for press | SYSTEM + `session.brought_note` | code + test_chat_session | changed | "the card is in the thread" → "its card is waiting for them" / "on the page": "thread" is our word, and the card is not always above (front-door `job=` flow draws it after). |
| Model-facing notes (tapped word, sentence, brought) | `session.py` 525–635 | code | reviewed | Instructions to the model, not shown. |
| Refused hosts | `prompts.shut_hosts` | code | reviewed | |
| Checked line (connector's record_turn) | `chat/check.py` ASK | code | reviewed | Hebrew-writing contract; not touched. |
| Saved conversation as a text | `transcript.py`, `record.py` | code | could not verify | Speaker label defaults to lowercase "you" when no name is passed; did not see how the reader page renders it. |
| Telegram: link (/start token) | `telegram.linked`, `telegram.link-expired` | code + rendered + tests | changed | "linked to your targum." → "This chat is now linked to your targum account." |
| Telegram: not linked yet | `telegram.link-first` | rendered | changed | → "Link this chat to your targum account first: {link}" (no period glued to the URL). |
| Telegram: /stop, not linked | `telegram.stopped`, `telegram.not-linked` | code | reviewed | |
| Telegram: what to send / unreadable | `telegram.what-to-send`, `telegram.cannot-read`, `telegram.name.*` | rendered | changed | Added "a link": the bot takes links (`_quote_link`). `you.telegram.says` has the same omission (account slice). |
| Telegram: quote + button | `telegram.quote.*`, `telegram.untitled`, `telegram.build` | rendered (empty / long / Hebrew / 1 / many) | changed | Button "Build" → "Open this": §12 2026-09-11 (a text is getting ready, never built), and the same press as the chat card. Flags below. |
| Telegram: started / press states | `telegram.started`, `telegram.pressed-already`, `telegram.press-stale` | rendered + tests | changed | started now says the link follows progress (it is /build/<id>, not the shelf); pressed-already → "We're already getting it ready."; press-stale said "Send the link again" but the button is also offered for long recordings → "Send it to us again." |
| Telegram: errors | `telegram.failed`, `telegram.too-big`, `telegram.no-address`, `telegram.in-library`, `telegram.already`, PDF page TargumError | rendered | reviewed | |
| Telegram linking on the account page | `you.telegram.*` | code | reviewed (not my keys) | Fine; `says` omits links. |

#### Layout / rendering flags (not fixed)
- Telegram quote with a Hebrew title: "מה קרה השבוע בכנסת. It's a text, so…" — the message starts with an RTL run, so Telegram may right-align it and put the full stop on the wrong side.
- Telegram quote title cut at 120 chars ends "…" and the template adds ".", giving "…."; a title ending "?" gives "?.".
- `telegram.too-big` fills `{name}` with the made-up file name, extension included ("Voice note.ogg is over 20 MB"); rare in practice.
- `f"{blocked} {address}/you"` (telegram.py) appends a bare URL to a refusal sentence.
- Reading drawer: "Reading" + a 90-char sentence + "Explain this sentence" on one row will wrap on a phone.

#### Terms
- **chat / conversation**: in-app surface uses "Conversations" (title, list button), "Conversation" (palette kind), "Continue in chat" (reader), "Chatting is included" (connect), and the model prompt says "conversation". Brief says "chat" is the word. Inconsistent; question raised.
- **getting ready / ready** for a text in progress (never "build"): Telegram button was the last reader-facing "Build" in this slice. Still reader-facing elsewhere: `shelf.status.building` "Building", `shelf.building.behind.*` "builds", `serve.we-lost-that-build…` (other slices).
- **the press button**: chat card "Open this" (`bring.read-this`), press page "Read this" (`press.page.read-this`), Telegram now "Open this". The press page should probably follow §6's neutral "Open".
- **known share**: "You know 82% of its words" (suggest line in chat, library/shelf) vs "about 8 words in 10" (card) in the same turn.
- **free**: "the library is always free" in `job.out-of.*` against §6 "inside the product there is no price".
- **credits**: consistent in this slice (Telegram quotes and the prompt).
- **Your words and phrases** (nav) vs "Your Words" (`yours.page.your-words`) vs "your words" — the claim note uses the nav's name, which is correct.

### Area: Copy audit: connect (targum in Claude, ChatGPT and other MCP apps)

There are no `approve.*` or `oauth.*` keys in the catalogue. The approval and refusal pages use `connect.page.*` and `connect.scope.*`. I reviewed all 190 `connect.*` keys, plus the English outside the catalogue in the owned files.

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| /connect header, nav, language switch | `connect.page.on-this-page`, `how-it-works`, `what-you-get`, `set-it-up`, `faq`, `sign-in`, `connect-targum`; connect.html.j2 | code | reviewed | The kicker literal "targum Connect" is the only place "Connect" is used as a product name. See Terms. |
| /connect hero and trust points | `connect.page.learn-hebrew`, `in-your-app`, `connect-targum-to-the-ai…`, `you-ll-need-a-targum-account`, `free-to-connect`, `set-up-in-two-minutes`, `disconnect-any-time`, `connect.head.*` | code | reviewed | Public page, so it is allowed to sell (§6). |
| /connect animated demo (3 scenes) | `connect.demo.*`, connect.js | code | reviewed | "Searching your targum library" searches the public library, not the reader's own, but it is only a demo label. "Added to your list to practise" uses "list" for mistakes (see Terms). |
| How it works (diagram and 3 steps) | `connect.page.ask-your-ai…`, `when-you-ask-about-hebrew`, `you`, `your-ai`, `write-in-hebrew-or-english…`, `your-ai-looks-at…`, `it-answers-at-your-level-and-targum-keeps-the-fixes` | code | changed | Step 3 said "targum keeps the lines it corrects", which reads as the AI correcting. `record_turn` has targum judge the line, and only lines it changed are kept. Now: "It answers at your level. targum checks what you write and keeps the corrections." |
| What you get (6 cards) | `connect.page.every-chat-starts…`, `new-to-targum`, `hebrew-at-your-level`, `the-fix-and-why`, `picks-up…`, `something-to-read-next`, `words-where-you-met-them`, `nothing-starts-without-you` | code | changed | `before-you-connect-we-show-you` said "you open it". Opening the link makes nothing: the reader confirms on the press or set page. Now: "…It can’t make a text on its own: it sends a link, and you confirm it on targum." The claim "Nearly 500 free texts and videos" is **could not verify** (see questions). |
| Set it up: address + Copy, app tabs | `connect.page.connect-in-two-minutes`, `pick-your-app…`, `copy`, `your-app`, `another-app` | code | reviewed | |
| Steps: Claude | `connect.page.claude-*`, `in-claude` | code | reviewed | These name third-party menus. They match connect.js's imitation of Claude's UI, and I could not check them against the live apps. |
| Steps: ChatGPT | `connect.page.chatgpt-*`, `in-chatgpt` | code | reviewed | "Developer mode is on ChatGPT’s paid plans" is a fact about a third party that I could not verify. |
| Steps: Claude Code, VS Code, Gemini CLI, Codex, another app | `connect.page.code-*`, `vscode-*`, `gemini-*`, `codex-*`, `other-*`, `sign-in-in-your-browser-then-connect` | code | changed | `codex-then-sign-in`: removed a stray comma. Terminal output lines in connect.js imitate each tool's own output and were left alone. |
| What it sees + example approval card | `connect.page.what-it-sees`, `you-see-what-it-can-do…`, `when-you-connect-we-show-you`, `we-only-see…`, `nothing-from-targums-chat…`, `example-the-page-you-approve-on`, `chatting-is-included` | code | reviewed | |
| FAQ | `connect.page.q-*` / `a-*` | code | changed | `a-can-it-spend-on-its-own` promised "press Start on targum", but no such button exists: the press page says "Read this" and the set page "Confirm". It also said the AI "tells you how long it’ll take", but the tool returns credits and length, not a wait. Now: "No. When you ask for a text, it sends you a link. Nothing is made until you confirm it on targum." `a-what-does-it-cost` does not say what "included" is included in (see questions). |
| Waitlist footer | `connect.page.learn-hebrew-in-the-ai…`, `your-email`, `you-example-com`, `join-the-waitlist`, `we-re-opening-in-small-groups` | code | reviewed | |
| Setup screen mock-ups (animated) | `connect.screen.*`, connect.js | code | reviewed | |
| Approval page, first-time connect | approve.html.j2; `connect.page.connect-to-targum`, `this-app`, `it-will-be-able-to`, `connect`, `not-now`, `then-we-ll-send-you-back-to`, `you-can-disconnect-it-later` | code + rendered (test_oauth_serve renders it) | reviewed | Buttons name their actions: Connect / Not now. |
| Approval page, scopes | `connect.scope.library`, `.record`, `.chat` = `oauth.SCOPES` (tests hold both copies to the same words) | code | needs input | The `chat` line sits under "It will be able to:", so the app becomes the subject of "keep the lines we correct". The line is also one long comma list, and "add a language you practise" is unclear. It omits adding an already-made text to a playlist with no confirm (`add_to_playlist`). I did not apply a fix because this is the wording a reader consents to. See questions. |
| Approval page, cost of `chat` | `connect.page.we-read-what-you-write` | code | reviewed | Says "Chatting is included" and gives no credits or hours, following §12 2026-09-24 ("The grant is one press, and chatting is included"). test_mcp_http pins that "hours" does not appear. |
| Approval page, reader signed out | serve `_oauth_authorize` → signin page + `targum_connect` cookie | code | could not verify | The sign-in page does not say why the reader is signing in (e.g. "Sign in to connect Claude"). The return trip relies on a cookie that lasts CONNECT_MINUTES in the same browser. If the reader opens the email link in another browser, or after the cookie has expired, they land on Learn and the connection is silently dropped. This is a material gap, but it belongs to the sign-in slice and needs a behaviour change. |
| Refusal: "Not now" | serve `_oauth_approve` → 303 to the app with `access_denied` | code | reviewed | targum shows no page. The app shows its own message. |
| Invalid or unverifiable connect link | connect_refused.html.j2; `connect.page.we-couldn-t-finish-that`, `your-app-sent-a-request…`, `how-connecting-works` | code + rendered (test) | reviewed | Takes ownership, gives a next step, and does not blame the reader. |
| Expired / invalid token, expired code | serve `_mcp` 401 + `WWW-Authenticate`; `/oauth/token` JSON errors | code | reviewed | These go to the app, which re-authorises. The reader sees the app's own UI. The `OAuthError` descriptions in oauth.py are for developers and never reach the page (serve logs them). |
| Revoked access | account page `you.connections.*`, `you.page.connections-says` (account slice) | code | reviewed | Not in my slice. The wording is fine. It sums up the scopes in different words ("your words and mistakes", "chatting in the language you're learning, which is included"). That is acceptable as a summary. |
| MCP JSON-RPC errors | mcp_http.py (`RpcError` texts, "Something went wrong on our side. Try again later.") | code | reviewed | Only the internal error is plausibly shown to a reader, and it is fine. |
| MCP server instructions | `mcp_http.INSTRUCTIONS` | code | reviewed | Instructions to the model only. No reader-facing sentence in it. |
| MCP prompts (the menu a host shows) | `mcp_http.PROMPTS[*].description` | code | changed | `talk`: "Talk in Hebrew, at your own words, …" became "Talk in Hebrew, using the words you know, with the translation when you ask." The `says` bodies are behavioural and were not changed. |
| Tool titles (hosts show them) | chat/tools.py `title=` | code | reviewed | "Check what I wrote" and "How to talk with me" are in the reader's voice. They are fine. |
| Tool errors relayed to the reader: record_turn | chat/tools.py `record_turn`, `_not_yet` | code | reviewed | Accurate about nothing being used on failure. `claim_turn` refusals come from the rails (credits/jobs slice). |
| Tool errors: quote_build language | chat/tools.py `quote_build` | code | changed | "X is not in the reader's profile." There is no "profile" in the product, and the error gave no next step. Now: "X isn't one of the reader's languages. They can add it on targum, under Your languages." (`you.page.your-languages`). Updated the pin in tests/test_chat_tools.py. |
| Tool errors: unreachable / bot-checked site | chat/tools.py `_shut` | code | changed | Both said a text couldn't be "built", which is the word the host is told never to use. Now: "…targum can't read the page or make a text from it" and "…but targum can't make a text from it." |
| Tool errors: sets, playlists, links, describe_source, fallback | chat/tools.py `quote_set`, `add_to_playlist`, `_too_many_playlists`, `_describe`, `run` | code | reviewed | These are written for the model ("the reader…") and the host paraphrases them, as INSTRUCTIONS asks. The notes say "Confirm" and "untick", which match the set page (`set.page.read-these`, `you-asked-for-these-somewhere-else`). |
| Tool results: my_hours rate line | chat/tools.py `CREDIT_RATE` | code | reviewed | Uses credits, with the rate given. |
| stdio `targum mcp` | connector.py `TargumError("The connector needs the mcp package.", …)` | code | reviewed | Developer-facing. |

#### Layout flags
- `connect.scope.chat` is a 30-word list item on a narrow card. It wraps to 4–5 lines on a phone, both on the approval page and in the example card on /connect.
- In the /connect hero, "Learn Hebrew / in [rotating app name]" will be tight next to the longest rotor names ("Claude Code", "Gemini CLI") at 320px. I could not verify this without rendering.

#### Terms
- **Connect / connector / app / your AI**: /connect uses "your AI" for the assistant and "app" for the client. "connector" appears only where the third-party menus use it. The kicker "targum Connect" treats Connect as a product name. Elsewhere the thing is "targum in Claude and ChatGPT", and the site foot calls it "Install MCP" (§12 2026-09-28). There are three names for one thing. Report only.
- **Confirm vs press vs Read this**: the connector's host notes say "confirm", the set page button is "Confirm", and the single-text press page button is "Read this". /connect now says "confirm", which fits both.
- **"your list"** means the word list ("Your list lives in targum", "Reading your targum list"), but also mistakes ("The mistake goes on your list to practise", "Added to your list to practise"). /connect counts them separately ("words known", "mistakes to practise"). This is minor drift.
- **Chatting is included** is consistent across the approval page, /connect FAQ, the `my_hours` rate line, the `record_turn` description and the account page.
- **Outside this slice:** `press.page.that-quote-has-gone-stale` ("That quote has gone stale…") puts "quote" inside the product, which §6 and §12 forbid. The press page is the page a connector's link opens. Report only.

### Area: Copy audit: account, settings and chrome

Slice: `you.*`, `account.*`, `signin.*`, `nav.*`, `foot.*`, `lang.*`, `language.*`, `date.*`, `waitlist.*`, `palette.*` (191 catalogue keys, all reviewed), plus the user-reachable `ValueError`s in `accounts.py` and a review-only pass of `legal.html.j2`.

Changed: 12 catalogue strings (`changes/account.json`) and 1 `accounts.py` message ("Keep at least one." is now "Keep at least one language ticked.", the same text as `you.keep-one`). Test pins updated: `tests/test_serve.py` (2), `tests/test_you_js.py` (1).

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| Sign-in page: blank form | `signin.html.j2`, `signin.page.*` | rendered | reviewed | The h1 is the tagline "Hebrew, with the translation beside it". Nothing on the page says "Sign in" except the foot link, which points back to this same page. See Q4. |
| Sign-in page: Continue with Google / "or" | `signin.page.continue-with-google`, `.or` | code | reviewed | Only shown when Google is configured. |
| Sign-in page: link sent (JS) | `signin.js`, `account.sent` | code | reviewed | Accurate. The server returns `sent` only after `mailer.send` succeeds, and uninvited addresses get a 403 instead. **Gap:** `script_strings(language, "signin.")` hands the page only `signin.*` keys, so `account.sent` / `account.could-not-send` always fall back to English on a Russian sign-in page. |
| Sign-in page: link sent (no JS) | serve `SENT` = "Thanks. Check your email." | code | reviewed | Not in my files. |
| Sign-in page: network failure | `signin.unreachable` | code | reviewed | |
| Sign-in: bad address / too many / mail failed | `serve.we-couldn-t-read-that-as`, `serve.we-ve-sent-a-few-links`, `serve.we-couldn-t-send-the-link` | code | reviewed | These are `serve.*` keys, outside my prefixes. They read fine. |
| Sign-in: address not invited | `serve.py` `NOT_OPEN` literal: "Thanks for asking. targum isn't open yet." | code | needs input | Not in my files. There is no next step: it doesn't point to the waitlist. It is also shown to an account that is closing (see Q3). Q2. |
| Emailed link: landing page ("Sign in as …") | `signin.page.sign-in-as`, `.press-to-sign-in-on-this-browser`, `.didn-t-ask-for-this-you-can` | rendered | reviewed | This covers the "wrong browser" case: the press signs in whichever browser opened the link. |
| Emailed link: used or expired | `signin.page.that-link-has-been-used`, `.each-link-works-once-for-twenty-minutes` | rendered | changed | The heading said "has been used" but the page is also shown for a link past its 20 minutes (`LINK_MINUTES`). It now reads "That link no longer works", and the body says to enter an email. |
| Google sign-in trouble (took too long, cancelled, didn't finish, refused) | `serve.that-sign-in-took-too-long`, `serve.no-harm-done`, `serve.that-sign-in-didn-t-finish` | code | reviewed | `serve.*` keys, outside my prefixes. Fine. |
| Account panel (corner), signed out | `_nav.html.j2`, `nav.your-words-follow-you-no-password-we`, `nav.send-a-link`, `nav.you-example-com` | code | reviewed | |
| Account panel: sending / sent / failed | `account.sending`, `.sent`, `.check-email`, `.could-not-send` | code | reviewed | |
| Account panel: `?signin=welcome` | `account.welcome` | code | reviewed | |
| Account panel: `?signin=expired` | `account.expired` | code | changed | Nothing in the server sets `signin=expired` any more, so this path is dead. It now matches the sign-in page wording. |
| Account panel, signed in: who, credits balance with rate | `account.credits.left.*`, `account.credits.rate`, `account.hours.*`, `account.minutes.*`, `account.hours.resets` | code | reviewed | Follows §12 2026-09-23: rate beside balance, "about {clock} of audio". The "resets {date}" line is on Your Progress only. `date.*` builds that date. |
| Account panel links | `nav.your-words-and-phrases`, `.your-subscriptions`, `.your-playlists`, `.your-profile`, `.sign-out`, `.find-anything` | code | reviewed | Naming inconsistency: see Terms. |
| Account button labels (a11y) | `account.yours`, `account.sign-in`, `nav.your-account` | code | reviewed | |
| Credits and billing | whole tree | code | reviewed | **There is no billing, payment or subscription surface.** No Stripe or checkout, no /pricing route, no failed-payment path. The only billing links are operator-side, to API consoles in `services.py` and the back office. Terms 2.1 says the Service is "without charge". The only per-reader money-like thing is the monthly credit allowance (`UPLOAD_SECONDS`). §6 still says "the reader pays by the month" (Q5). |
| /you, signed out or server unreachable | `you.page.sign-in-from-the-corner-and-we` | code | reviewed | Also shown when `/account/me` fails for a reader who is signed in (the `.catch`), so an offline reader is told to sign in. Behaviour, not copy. |
| /you: name, Hebrew address | `you.page.name`, `.what-should-we-call-you`, `.in-hebrew-targum-calls-you`, `.either`, `you.saved`, `you.signed-out` | code | reviewed | |
| /you: languages | `you.page.your-languages`, `.learning`, `.translations-in`, `.hebrew-is-always-on-…`, `you.keep-one`, `accounts.py` `choose()` | code | changed | The note under both lists said "Everything else is experimental". English translations are not experimental (`INTO`: en alpha). "Keep at least one." now names what, in the page and on the server. "You lose nothing when you untick one" is kept but not verified: Q6. **Bug (not copy):** `saveLanguages` shows a refusal without the `bad` flag, so the error is in ink, not clay. |
| /you: languages, server refusals | `accounts.py` "We don't offer {X}.", "{Hebrew} stays on.", "No such choice.", "{X} isn't one of your languages." | code | reviewed | Only reachable from a stale or tampered page. They are English-only (not in the catalogue), so a Russian reader gets English. |
| /you: your reading tally | `you.kept`, `you.kept.words.*`, `you.kept.phrases.*`, `you.page.your-reading`, `.your-progress`, `.has-the-whole-of-it` | code | changed | "has the whole of it" is now "has the details". |
| /you: what we record (stop / start / erase / erase for good) | `you.page.what-we-record`, `.record-says`, `.record-erase`, `you.record.*` | code | reviewed | Agrees with Privacy 3.6 and Retention 1.8. |
| /you: correcting a meaning (grant) | `you.page.correcting*`, `you.grant.*` | code | reviewed | Consent text; left alone. It matches Privacy 3.8. |
| /you: what's connected | `you.page.what-s-connected`, `.connections-says`, `you.connections.*` | code | reviewed | |
| /you: Telegram | `you.telegram.*` | code | changed | "never who sent it first" was cryptic. It now says a forwarded message's sender isn't kept, as Privacy 3.9 says. |
| /you: your prompts | `you.page.your-prompts`, `.prompts-says`, `.prompt-*`, `you.prompts.*` | code | reviewed | |
| /you: your subscriptions (followed series) | `you.page.your-subscriptions`, `.series-that-come-out-on-their-own` (+ `follow.*`, not mine) | code | changed | "on their own clock" is now "on a schedule". The email claim is checked: `series.mailed` covers weekly or slower. The call site was a multi-line literal and was joined by hand. The name clashes with a paid subscription: Q5. |
| /you: download, sign out, delete (ask twice, keep), closing, unreachable, seven days | `you.page.download-your-words`, `.sign-out`, `.delete-account`, `.keep-my-account`, `.we-wait-seven-days-before-deleting`, `.what-that-means`, `you.forget*`, `you.closing` | code | needs input | Accurate. The labels "Download your words" and "Delete account" are quoted in the legal text, so they must not change. **Gap:** a closing account can't be reopened in the product (`Store.stay` is never called, and sign-in refuses a leaving account). The legal page says to email hello@targum.page within seven days, but the page doesn't say so: Q1. |
| Test accounts | `accounts.py` `make_test_account`, `test_sign_in`, `_wipe_if_testing` | code | reviewed | Operator CLI only. The `ValueError` text goes to the operator's terminal, not a reader. Signing out of a test account wipes it silently, with no reader-facing copy. That fits, since the testers know. |
| Waitlist: join reply (every state) | `waitlist.note.check-your-email`, `.not-an-address`, `.too-often` | code | changed | The same reply goes to an address already on the list, which gets no mail. Added "If you're already on the list, there's nothing more to do." It stays identical for every address, so it still doesn't reveal who is on the list. |
| Waitlist: confirm page (GET) and confirmed (POST) | `waitlist.note.keep-me`, `.keep-me.button`, `.you-are-on` | code | changed | The address is pending at this point, so "keep … on the waitlist" was wrong. It now reads "Add {email} to the waitlist?". |
| Waitlist: link spent | `waitlist.note.link-spent` | code | changed | Adds the next step, and tells someone who pressed twice that they're on the list. |
| Waitlist: leave | `waitlist.note.take-me-off`, `.take-me-off.button`, `.taken-off` | code | reviewed | |
| Waitlist note page heading | `waitlist.note.heading` | code | changed | The h1 "the waitlist" is now "The waitlist". |
| Waitlist line in the foot | `_site_foot.html.j2` → `landing.page.join-the-waitlist` | code | reviewed | A `landing.*` key, excluded. |
| Nav bar, places | `nav.learn`, `.your-many`, `.targums`, `.library`, `.your`, `.progress`, `.add`, `.pages` | code | reviewed | |
| Nav: find, notifications, clear, empty | `nav.find-anything*`, `.find-a-text-a-page-a-conversation`, `.notifications`, `.clear-all`, `.we-re-not-building-anything-right-now` ("Nothing new.") | code | reviewed | |
| Talk to targum pill and drawer | `nav.talk-to-targum`, `nav.close` | code | reviewed | |
| Language menu | `lang.js`, `lang.*`, `language.*` | code | reviewed | `lang.beta-note` "is new here, and still experimental" never says what experimental means for the reader. Minor, left. |
| Command palette | `palette.js`, `palette.*` | code | reviewed | |
| Foot (app and public) | `_site_foot.html.j2`, `foot.*` | code | reviewed | "© 2026 targum · AGPL-3.0" is a literal. |
| Month names / date | `date.*` | code | reviewed | |
| Legal: privacy, terms, retention, deletion | `legal.html.j2` | code | needs input | Review only, nothing changed. Several gaps against the code: Q7. |
| Icons, glyphs | `_icons.html.j2`, `_glyphs.html.j2` | code | reviewed | No visible or a11y text. Controls that use the glyphs carry their own labels. |
| keep.js, sync.js, durable.js | assets | code | reviewed | No user-facing English. |

#### Layout flags (not fixed)
- `waitlist.note.link-spent` and `.check-your-email` are now three short sentences. They sit on a page of their own, so there is room.
- `you.page.hebrew-is-always-on-…` is now three short sentences in the `.note` under the ticks. It is fine at phone width, just a line longer.
- "Accept and turn it on" and "Delete my account and words" are the longest buttons (four and five words). Both are deliberate: consent and a confirm.

#### Terms
- **Credits**: "{n} credits left this month — about {clock} of audio". Consistent with §12.
- **The /you page has four names**: page title "You", tab "You — targum", the corner and palette link "Your profile", and the legal text's "the profile page". "Your account" is the corner's aria label and the heading of the page's last section. Recommend settling on one (see Q5).
- **"Your subscriptions"** means followed series (nav, palette, /you, `series.stop.heading` "your subscriptions" in lowercase). It will collide with a paid subscription if one ever exists.
- **Shelf vs Your targums**: the nav says "Your targums". The Telegram copy and the ready mail say "your shelf" (`you.telegram.says`, `telegram.*`, `mail.ready.*`). §6 calls "the shelf" a team word.
- **Conversation vs chat**: the palette kind is "Conversation", and the nav placeholder says "a conversation". "Chat" is the verb and the scope. Consistent with how the app uses the nouns elsewhere, so left.
- **Network errors**: "We couldn't reach targum. …" (5 keys, including `you.forget.unreachable`) against "We couldn't connect. …" (`signin.unreachable`, `reader.error.connect`, `chat.unreached`). Two patterns for one failure across the app.
- **Link states**: the sign-in and waitlist link pages now both say "That link no longer works". `telegram.link-expired` says "That link has expired." (not mine).

### Area: Copy audit — slice: mail

Scope: every mail targum sends to a person: catalogue keys `mail.*` (50 keys), `src/targum/letters.py` (all builders), `mail.py`, `doorway.py`, the mail half of `series.py`, `weekly/mailout.py` (the weekly announce), plus the confirm/stop pages each mail lands on (`weekly-note.html.j2`, `waitlist.note.*`, `weekly.note.*`). I read those pages only to check the sequence. They belong to another slice, and I changed nothing in them.

Renders: `scratchpad/copy/emails/<name>.before|after.html|.txt`, made by `emails/render.py` from the builders with realistic data: a long Latin title, a Hebrew title, an empty title, read/listen/watch, asked vs. not asked, with and without the connector paragraph, an issue with a blurb and three levels, an issue with no blurb and one level, a series with and without Hebrew, and a non-catalogue language (`de`) falling back to English. The worktree has no `.venv`, so I ran them with the main checkout's interpreter and `PYTHONPATH` set to the worktree's `src`. Nothing in the main checkout was changed.

Every mail goes out from `targum <hello@mail.targum.page>` with Reply-To `targum <hello@targum.page>` (`mail.py` SENDER/REPLY_TO; env can override both). Every mail is multipart/alternative (text + HTML) built from one list of blocks. The foot always ends with "targum · {host}".

#### Inventory

| Surface / state | Where (file or key prefix) | How checked | Status | Notes |
|---|---|---|---|---|
| **Sign-in link.** Trigger: POST `/account/signin` → `serve._sign_in` → `SmtpMailer.send` → `letters.sign_in` | `mail.sign_in.*`, `mail.fallback` | rendered | reviewed | Subject 24 chars. Preheader 39. Heading "Sign in to targum". Lead gives the 20 minutes, which matches the TTL in `accounts.py` (twenty minutes, single use). Button "Sign in". Fallback link: yes. Foot "Didn't ask for this?…". No list headers (correct, transactional). The lead says "Press the button", and the plain-text part has no button, only "Sign in:" and the link. That is minor and left alone. |
| Sign-in, local console | `mail.py` `ConsoleMailer.send` | code | out of scope | Only the operator reads this, in their own terminal (always English, by design). |
| **Waitlist confirm (double opt-in).** Trigger: POST `/waitlist` → `serve._waitlist_post` → `letters.waitlist_confirm`, in the language of the door | `mail.waitlist.*`, `mail.confirm`, `mail.fallback`, `mail.not-you` | rendered | **changed** | The preheader "One press and you're on the list." and the lead "Press Confirm and you're on the waitlist." were inaccurate. The mail's Confirm opens `/waitlist/confirm`, a page that asks "Should we keep {email} on the waitlist?" with a second Confirm (so that a link-fetching mail client cannot answer). The preheader is now "Confirm your email address to join the waitlist." (48) and the lead "Press Confirm to finish joining the waitlist." Subject 41. "Didn't sign up? Ignore this email and you won't hear from us again." is accurate: only confirmed rows are ever invited (`waiting_for_a_way_in`: `state='on'`). |
| Waitlist confirm page (after the mail) | `waitlist.note.keep-me*`, `waitlist.note.you-are-on`, `waitlist.note.link-spent` | code | reviewed (not my slice) | "You're on the list. We'll email you when it's your turn." This agrees with the mail's "we'll email you when it's your turn". `link-spent` says "or it's expired", but confirm tokens never expire (`confirm_waiting` has no time check). Reported to the page slice. |
| **Invitation off the waitlist.** Trigger: `targum open-the-door` (CLI) or the admin "let in" button (`serve._let_in`) → `doorway._let` → `letters.invitation`, in the language they joined in | `mail.invitation.*` | rendered (connector on, off, `de`→English) | **changed** | Subject "It's your turn: targum is open for you" (38). Preheader "Sign in with this email address to start." (41; "this address" was ambiguous in a mail full of URLs). Lead: "…Sign in with this email address and we'll send you a sign-in link." ("email you a link" said email twice and did not say which link). In the connector paragraph I made the apostrophes straight, because they were the only curly ones in the mail. `free`, `button`, `reply`, `why` were reviewed and are fine. "The library is free to read, and there's no card to add" matches the landing page's claims. Layout flags: (1) the `/connect` URL in the connector paragraph goes out as bare text inside `Para`, so it is not a link in the HTML (most clients autolink it, and some do not). (2) The invitation has no Fallback block under its button, unlike the other button mails. |
| Invitation → sign-in sequence | — | rendered | reviewed | Invitation ("Thanks for waiting", button to `/account/signin`) → the reader types their address → sign-in mail (no "thanks for waiting" again). Nothing contradicts. "We're opening in small groups" appears in the waitlist mail and again in the invitation's reply line. That is consistent, not repeated thanks. |
| **Weekly News Digest confirm.** Trigger: POST `/weekly/subscribe` → `serve._weekly_post` → `letters.weekly_confirm` | `mail.weekly.confirm.*`, `mail.confirm`, `mail.fallback`, `mail.not-you` | rendered | **changed** | The same two-press inaccuracy. Preheader "One press and it arrives every Monday." → "Confirm your email address to get it every Monday." (50). Lead "Press Confirm and the Weekly News Digest arrives every Monday" → "Press Confirm to get the Weekly News Digest every Monday: …". Subject 44. The landing page asks "Should we send the Weekly News Digest to {email} every Monday?" [Confirm], then says "Thanks. You'll get the Weekly News Digest every Monday." That is consistent. |
| **Weekly News Digest issue.** Trigger: `targum weekly announce <week>` (CLI) → `weekly/mailout.announce` → `letters.weekly_issue`, per subscriber language | `mail.weekly.*` (+ `weekly.level.*`, `weekly.page.figure-words`) | rendered (3 levels + blurb; 1 level, no blurb) | reviewed; 2 flags | Subject "Weekly News Digest · Monday, September 28, 2026" (47; a long month name reaches about 50). The preheader is the issue's Hebrew blurb; "The week's news in Hebrew, at three levels." is used only when there is no blurb. That fallback is **inaccurate when an issue has fewer than three editions** (the one-level render). This is a rare edge case and was not changed. Body: date label, Hebrew title, Hebrew standfirst, button "Read this week's issue", "Choose your level" and one row per level: "Easy (1,000 words)". **Flag:** "1,000 words" is a vocabulary size, but a newcomer will read it as the article's length. That key (`weekly.page.figure-words`) is outside my slice. Foot: why + "Unsubscribe" link, plus List-Unsubscribe/One-Click/List-Id headers, plus a postal-address slot. The title, blurb and editions come from the weekly's private writer (`weekly/write.py`), which is gitignored and **absent from this worktree**, so I could not audit the writer's Hebrew or its prompts for English. |
| **Series instalment** (a followed weekly-or-slower series; in practice only the weekly portion, since daily cycles are never mailed and the digest has its own mailout). Trigger: the `serve` background thread `keep_telling` → `series.announce` → `series.letter` → `letters.series_instalment`, hosted only | `mail.series.*` | rendered (parasha with Hebrew; long title without Hebrew) | reviewed; flags | Subject "{name}: {title}", e.g. "The weekly portion: Bereshit" (28). Preheader and lead are both "The new instalment is ready." Button "Open" (neutral, correct per §6: a series' verb is not known). Foot "You're getting this because you follow The weekly portion on targum." The capital "The" mid-sentence comes from the series name, and I left it. The stop link reads "Stop these emails", while the digest's reads "Unsubscribe". Both are clear, and the two words differ (see Terms). The List-Id display name is the raw id ("parasha <parasha.series…>"), not the series name. That is a code nit, not copy. |
| **Build ready.** Trigger: `Library.tell(job)` in `serve.py` when a build finishes and either the reader put the strip away with "email me" (`asked`) or it ran longer than `LONG_BUILD_MS` (about 3 min) | `mail.ready.*` | rendered (read/why, listen/asked, watch/asked, empty title in `de`) | reviewed; 1 question | Subject "Ready to read/listen/watch: ⁨{title}⁩". It exceeds 50 chars with a long title, but the main point comes first, so truncation loses only the title's tail. The label follows the verb, and so does the subject. Lead "Thanks for waiting. It's on your shelf now." (the preheader is its second half). Button "Open". Foot: "asked" → "…because you asked us to email you when it was ready". Otherwise "…because your text took more than a few minutes to build" (kept by David per §12, even for a video). An empty title renders "Ready to read: ⁨⁩", but serve always passes `job.title or job.source`, so it cannot happen. |
| Sign-in → pages / ready mail vs. the page | — | code | reviewed | The ready mail is sent only after the build is on disk (`tell` requires `job.reader`), so "It's on your shelf now" is accurate. Nothing tells the reader twice. |
| Language fallback | `letters._code` + `strings.text` | rendered (`de`) | reviewed | An uncatalogued language falls back to English for every string, and `<html lang="de">` is still declared with English words. That is a small accessibility mismatch (screen readers may use a German voice) and a code matter. Flagged, not changed. |
| Operator alerts (health down/up, backup) | `alerts.py` `step`/`tell` | code | out of scope | Operator-only, English, plain text. Not reviewed for voice. |
| Doorway / let-in errors | `doorway.py` ValueErrors, `serve._let_in` messages | code | out of scope | Operator-only (CLI and back office). |
| series.py series names/blurbs | `series.py` `_weekly`, `_parasha` literals = `series.*.name/what` | code | reviewed (not my keys) | These literals are fallbacks for the `series.*` keys. They are used in the mail's label, subject and foot, and they match the catalogue. |
| weekly-note.html.j2 | template | code | not mail | It is the landing page a mail link opens (confirm and stop). It belongs to the page slice. Its only literals are catalogue calls (`note.read-this-week`, `note.back-to-targum`). |

### Mobile / narrow width (from the HTML)
- Card max-width is 600px. At ≤620px the padding drops to 24/20px and h1 to 20px. That is fine.
- Buttons are inline-block pills with 28px side padding, and every label is 1–4 words (the longest is "Read this week's issue", about 200px). None overflows at 320px.
- The fallback URL has `word-break:break-all`, so a long token wraps without horizontal scroll.
- Titles have no `nowrap`, so long titles wrap. The Hebrew title is 26px/40px `dir=rtl` and wraps correctly.
- Subjects: every fixed subject is ≤ 47 chars. The ready and series subjects grow with the title (97 chars in the long-title render), with the verb first. Preheaders are all ≤ 50, except the digest's, which is the issue's own blurb.

#### Terms
- **Confirm.** Used for both double opt-ins, and the landing pages' button is also "Confirm". That is consistent, but it is two presses (see changes).
- **waitlist / the list.** Mail and pages mix "waitlist" and "the list" ("You're on the list"). They are close enough.
- **Unsubscribe vs. Stop these emails.** The digest's foot says "Unsubscribe", the series foot says "Stop these emails", and the stop pages say "Yes, stop". The same action has two names. I recommend one ("Unsubscribe" is the word people look for). I did not change it, because both are clear and it is churn in two languages.
- **Weekly News Digest.** Consistent in every mail. The `series.weekly.what` blurb says "written three ways", while the mails and pages say "at three levels". Report only.
- **instalment** (British spelling). This is the app-wide word for a series' new item. Readers who follow a series know it.
- **shelf.** "It's on your shelf now" matches the product's term.
- **sign-in link.** Used in the sign-in subject and now in the invitation lead.
- **"text"** in "your text took more than a few minutes to build" covers audio and video too. That is deliberate per §12.

### Area: Copy audit: publications slice

Scope decision. design.md §6 names "the weekly's front" a public, selling page, and §12 (2026-09-27, "The weekly, the parasha and the dailies are drawn as the front door is") rebuilt all three from the landing's parts: the landing bar, a hero with the waitlist form, a "Why targum" pitch, and the landing's closing waitlist section. So each of these pages **mixes** both kinds:
- **Excluded (marketing):** the hero (headline, lede, waitlist form, press line), "Why targum" and the closing waitlist. Those are the landing's sections, or copies of them, and I left them untouched.
- **In scope (reading chrome):** everything a reader uses to read. That covers the labels, datelines, level ladder, full-screen handle, aliyot list, te'amim switch, Israel/diaspora switch, haftarah, portion navigation, other days, credits ("Made honestly"), sources, archive, and the confirm/stop pages.

`press.*` / `press.html.j2` / `press.js` is **not the press kit**. It is the in-product page where a reader confirms a build that Claude/ChatGPT set up over MCP (`/build/<id>`), so I reviewed it in full. `about.*` is the small "under construction" page that the foot's About link opens. It sells nothing, so it is in scope.

| Surface / state | Where | How checked | Status | Notes |
|---|---|---|---|---|
| Weekly: hero (headline, lede, waitlist, "Read this week's issue", press line) | weekly.html.j2 `.front-hero`; `weekly.page.read-this-week-s-*`, `from-this-week-s-reporting-in` | code | excluded (marketing) | On an **archived** issue these say "this week's", which is false. See questions Q2. |
| Weekly: section label | `weekly.page.this-week` | code, rendered (test) | changed | "This week" → "This issue" (it also heads archived issues). Pin updated in test_weekly_public.py. |
| Weekly: dateline | `weekly.page.every-monday-…` | code | changed | Dropped "This is this week's" (false on archives). "written three times over" → "written at three levels. Pick one:". Multi-line literal edited by hand to match. |
| Weekly: level ladder (names, count, explanation) | `weekly.level.*`, `weekly.level.*.explained`, `weekly.page.for`, `weekly.page.figure-words`, ladder aria-label | code | changed | "for 1,000 words" → "if you know 1,000 words" (the word "for" is hidden on a phone, so phones still show "1,000 words"). Took jargon out of the three explanations ("register", "subordinate clauses", "Officialese", "constructions"). `builder.WEEKLY_LEVELS` mirrors these and was hand-synced. |
| Weekly: full-screen handle | `weekly.page.full-screen`, `weekly.full-screen`, `weekly.back-to-page` (weekly.js) | code, rendered (test pin) | changed | Exit label "Back to the page" → "Exit full screen", now the same on all three pages. Pin updated. |
| Weekly: framed reader title | iframe title (`{title} — {level} · {figure} words`) | code | reviewed | |
| Weekly: "Why targum" | `weekly.page.why-targum` … `vowel-points-on-or-off…` | code | excluded (marketing) | |
| Weekly: Made honestly / Sources / "Read the whole thing" | `weekly.page.made-honestly`, `sources`, `read-the-whole-thing` | code | reviewed | "Read the whole thing" opens /add?source=, where the cost is shown before anything is spent. Accurate. |
| Weekly: archive | `weekly.page.earlier` | code | changed | "Earlier" → "Earlier issues". |
| Weekly: empty / missing | serve.py `_serve_weekly` | code | reviewed | No issue, unknown week or unknown level gives a **plain-text "not found" 404**, not the designed 404 page. See the route table. |
| Weekly News Digest: confirm page (GET /weekly/confirm) | `weekly.note.send-it`, `.button`, `weekly.note.heading` | code | reviewed | |
| Digest: confirmed | `weekly.note.you-are-on` | code | reviewed | |
| Digest: link spent | `weekly.note.link-spent` | code | reviewed | No next step. The page's button leads to /weekly. I left it: the only way back in is to follow from Learn when signed in, and I can't point a signed-out subscriber there accurately. |
| Digest: stop page / stopped | `weekly.note.stop-it`, `.button`, `weekly.note.stopped` | code | reviewed | Deliberately says the same thing for any token. |
| Digest: subscribe POST states (bad address, too often, check email) | `weekly.note.not-an-address`, `too-often`, `check-your-email` | code | reviewed | **No page posts to /weekly/subscribe any more.** The weekly's form is now the waitlist's, so these states are reachable only by a hand-made POST. |
| Note page furniture: title, description, back button | `weekly.note.title`, `weekly.note.description`, `note.read-this-week`, `note.back-to-targum` (weekly-note.html.j2) | code | reviewed | **Bug:** `builder.weekly_note` always sets `<title>` "Weekly News Digest — targum" and the digest's description, including on the waitlist and series-stop pages that reuse this template. Flagged, not fixed (builder logic). |
| Parasha: hero (eyebrow, headline, lede, waitlist, "Read {name}") | `parasha.page.this-shabbat`, `pitch-this-week`, `daily.page.pitch`, `the-hebrew-as-the-masorah…`, `parasha.page.read` | code | excluded (marketing) | |
| Parasha: "The reading" label and dateline, festival/doubled notes, plurals | `parasha.page.the-reading`, `dateline`, `verses.*`, `aliyot.*`, `festival-instead`, `two-portions` | code | reviewed | |
| Parasha: this week's parts list | `parasha.page.this-week-s-reading`, `read-2` ("· read") | code | reviewed | |
| Parasha: te'amim switch | `parasha.page.the-chanting-marks`, `with-the-te-amim`, `as-it-is-chanted`, `every-mark…`, `vowels-only`, `easier-to-read`, `the-chanting-marks-taken-off…` | code | reviewed | Three terms for one thing: chanting marks / te'amim / cantillation. The explanation line glosses them, so I left it. See Terms. |
| Parasha: Israel/diaspora switch | `israel-and-the-diaspora…`, `diaspora`, `israel` | code | reviewed | |
| Parasha: full-screen handle | `parasha.page.full-screen`, `parasha.full-screen`, `parasha.close` (parasha.js) | code | changed | "Close" → "Exit full screen". |
| Parasha: haftarah label, dateline, frame title | `parasha.page.the-haftarah`, `haftarah-title`; **literal** "— from … , N verses. Read this week in place of the portion's own: …" | code | reviewed | The dateline's English is a template literal, not in the catalogue, so it stays English on a Russian page. Flagged. |
| Parasha: portion navigation | `the-other-portions`, `previous`, `all-portions`, `next` | code | reviewed | |
| Parasha: "Why targum" | `parasha.page.why-targum` … `words-you-mark-here…` | code | excluded (marketing) | |
| Parasha: Made honestly | `parasha.page.made-honestly`, `made-honestly-says` | code | changed | "cut to this week's reading" → "cut to this reading" (the paragraph also stands on the 54 named-portion pages). `translation_said` is a builder literal, English only, and says "matched … on this machine", which is odd for a web visitor. Flagged. |
| Parasha: credits | `parasha.page.credits-say`, `photographed-by-jacob-gucker` | code, rendered (test) | changed | The old wording put the scroll itself in the public domain. It now says "was photographed by …, and the photograph is in the public domain under CC0". Pin updated in test_parasha_page.py. |
| Parasha: every-portion list | `parasha.page.every-portion` | code | reviewed | |
| Parasha: missing portion / not built | serve.py | code | reviewed | Plain-text 404. |
| Daily: hero | `daily.page.today`, `daily.page.pitch`, `cycle.blurb` | code | excluded (marketing) | |
| Daily: dateline, other days, also today | `daily.page.other-days`, `also-today`, `rhythm-today` | code | reviewed | `cycle.rhythm` and `cycle.name` come from daily/cycles.py and are English only. |
| Daily: full-screen handle | `daily.page.full-screen` + parasha.js | code | changed | Via `parasha.close`. |
| Daily: Made honestly | `daily.page.made-honestly-says`, `a-published-translation`, `published-by` | code | changed | "cut to today's reading" → "cut to this day's reading" (also shown for other days). |
| Daily: cycles we don't carry | daily/cycles.py `ABSENT` | code | needs input | "its only free Hebrew is ShareAlike, which a build cannot carry onto what it makes" is jargon on a public page. The file is not in this slice. Suggested: "The Talmud isn't here: the only free Hebrew text is licensed ShareAlike, and we can't carry that licence onto what we build." |
| Daily: day outside window | serve.py | code | reviewed | Plain-text 404. |
| Page `<title>`/description (weekly, parasha, daily) | builder.py literals; `_public_head.html.j2` | code | reviewed | The parasha and daily titles and descriptions are English literals, not catalogued, so Russian pages get an English title and description. Flagged. |
| About page | `about.page.*` (about.html.j2) | code | reviewed | The calendar cell's hover `title` ("N change/changes") is an English literal. |
| Build confirm (press) page: ready to build | `press.page.read-this`, `ready-in-about-minutes.*`, `uses-credits.*`, `you-asked-for-this-somewhere-else` | code | needs input | "Read this" is on a button that spends credits, and it also shows over a video. See Q1. |
| Press: pressed / building | `press.page.we-re-making-it`, `getting-started`, `see-how-it-s-going`, `close-find-it-in-your-targums`, `go-to-your-targums`, `share-done`, `minutes-left.*`, `longer-than-usual`, `getting-it-ready` | code | changed | Fixed the template fallback for `getting-started` ("Getting started." ≠ en.json "We're getting it ready."). **Fixed a false error state:** after the press a job is `queued`, and the template sent `queued` to the "We can't make this one" branch. Every no-script press, and every reload while a build waited its turn, told the reader the build had failed. `queued` now draws "We're making it". This is one token in the template's condition; revert it if you'd rather keep the change out of a copy pass. |
| Press: ready → open | `press.page.this-one-is-ready`, `open-it`, `open-now`, `it-s-ready` | code | reviewed | |
| Press: failed / blocked / other | `press.page.we-can-t-make-this-one`, `that-quote-has-gone-stale`, `couldn-t-start` | code | changed | "That quote has gone stale. Ask again where you asked before." → "We couldn't get this one ready. Ask for it again where you asked before." Nothing in the code expires a quote, and "quote" is banned inside the product (§6 and the MCP instructions). Still wrong: the `looking up words` (pricing) stage also lands in this branch, and so would a job still `reading`. See Q1. |
| Shared head | `_public_head.html.j2` | code | reviewed | No copy of its own. |
| Shared foot | `_public_foot.html.j2` → `_site_foot.html.j2` (`foot.*`, `landing.*`) | code | reviewed | No copy of its own. The foot's strings belong to the account/nav slice and the landing. |
| Social links | `_social.html.j2` | code | reviewed | Platform names only. |
| Dead keys | `weekly.page.sign-in`, `weekly/daily/parasha.page.keep-what-you-learn`, `every-word-you-mark-remembered`, `in-next-week-s-issue-and-in` / `in-next-week-s-portion-and-in` / `in-tomorrow-s-reading…`, `an-email-address-no-password`, `daily.page.sign-in`, `parasha.page.sign-in` (15) | grep | reviewed | Nothing references them since the 2026-09-27 redesign. Not deleted, because deleting them touches ru.json. |

#### Layout flags (not fixed)
- The te'amim ladder puts "With the te'amim" in bold. On a phone the ladder becomes nowrap chips (`.ladder b { white-space: nowrap }`), so "With the te'amim" and "Vowels only" in two flex columns at 320px are tight. Worth a look.
- Weekly on a phone: the ladder's `.figure` is nowrap, so "5,000+ words" sits under a 0.8125rem bold name. It fits. The new "if you know" is hidden on a phone, as "for" was.
- The press page's `known_line` and title can be long English and Hebrew mixed in one `.said` line. The title has no `bdi`/`dir`, so a Hebrew title beside English punctuation may reorder.

#### Terms
- **Weekly News Digest** is the public name (§12). The weekly page itself never names it in the body. It says "issue" and "this week's issue", which fits. The digest's own `<title>` does use the name.
- **Level** names: Easy / Simplified / Native, consistent.
- **Full screen / Exit full screen:** now the same across the weekly, the parasha and the dailies. Before this pass the exit label was "Back to the page" or "Close".
- **Chanting marks / te'amim / cantillation / trope:** four words on the parasha page for one thing. The switch uses "te'amim" and its aria-label says "The chanting marks". The explanation mixes both. Acceptable for this audience, but "chanting marks" would be the newcomer's term.
- **Aliyah / aliyot, haftarah, leyning, Masorah:** used without a gloss. Fine for people preparing a Torah reading, not for a newcomer.
- **Your targums:** the press page uses it, consistent with §12.
- **Credits:** the press page uses credits, and I found no price or money on it. "Quote" appeared once ("That quote has gone stale") and is now gone. Elsewhere in the app, `set.page.*` ("We can't add this one") uses "add" where press says "make". Reported, not fixed.
- **"Read this"** for the build press, against §6's read / listen / watch / Open rule. See Q1.

#### Every serve.py route that returns an HTML page, and who covers it

"?" means I'm guessing the owner. **UNCOVERED?** means I think no slice has it.

| Route | Handler → template / builder | Slice |
|---|---|---|
| `/` signed in | `_desk("page")` → learn.html.j2 | learn |
| `/` signed out, front door open | `front_page` → landing.html.j2 | excluded (marketing) |
| any page route, signed out (door shut, or not `/`) | `holding_page` → holding.html.j2 | **UNCOVERED?** (account or add?) |
| `/add` | `_desk("adding")` → add.html.j2 | add |
| `/chat`, `/chat?embed=1` | `_desk("chatting"/"embedded")` → chat.html.j2 | chat |
| `/progress` | `_desk("progress")` → progress.html.j2 | learn? (confirm) |
| `/texts`, `/words`, `/phrases` | `_desk("lists:*")` → `list_page` (yours.html.j2 / lists) | library? (confirm) |
| `/library` signed in | `_desk("catalogue")` → library.html.j2 | library |
| `/library` signed out, shelves public | `shelf_page` → shelf.html.j2 | **UNCOVERED?** (public shop window, possibly marketing) |
| `/library` signed out, shelves shut | holding.html.j2 | see holding |
| `/library/<id>` | `text_page` → text.html.j2 | **UNCOVERED?** (public text page, possibly marketing) |
| `/you` | `_desk("you")` → you.html.j2 | account |
| `/playlists` | `_desk("playlists")` → playlists.html.j2 | library? (confirm) |
| `/reader/<…>` | built reader files (reader.html.j2, index.html.j2 contents) | reader |
| `/weekly/read/…`, `/parasha/read/…`, `/<cycle>/read/…` | built reader files (framed) | reader |
| `/weekly/<week>/<level>` (`/weekly`, `/weekly/<week>` redirect) | `weekly_page` → weekly.html.j2 | publications |
| `/weekly/confirm`, `/weekly/stop` (GET); POST `/weekly/subscribe`, `/weekly/confirm`, `/weekly/stop` | `weekly_note` → weekly-note.html.j2 | publications |
| `/parasha`, `/parasha/<slug>` | `parasha_page` → parasha.html.j2 | publications |
| `/mishna-yomi`, `/nach-yomi`, `/tanakh-yomi`, `/tehillim` (+ `/<date>`) | `daily_page` → daily.html.j2 | publications |
| `/about` | `about_page` → about.html.j2 | publications |
| `/build/<id>` GET (and no-script POST → redirect back) | `press_page` → press.html.j2 | publications (this is **not** the press kit) |
| `/set/<id>` | `set_page` → set.html.j2 | connect? (the sister of press) **confirm** |
| `/series/stop` GET/POST | `weekly_note` + `series.stop.*` | mail? **possibly UNCOVERED** (the template is mine; `series.stop.*` keys I did not review) |
| `/waitlist/confirm`, `/waitlist/stop` GET; POST `/waitlist`, `/waitlist/confirm`, `/waitlist/stop` | `weekly_note` + `waitlist.note.*` | **UNCOVERED?** Waitlist = front door. Excluded as marketing, or mail? The confirm/stop pages are transactional. |
| `/connect` | `connect_page` → connect.html.j2 | connect |
| `/oauth/authorize` | `approve_page` → approve.html.j2; `signin_page`; refusal → `connect_refused_page` → connect_refused.html.j2 (400) | connect |
| `/privacy`, `/terms`, … (`LEGAL_ROUTES`) | `legal_page` → legal.html.j2 | account |
| `/account/signin`, `/account/enter` (GET and POST), `/account/google/back` refusals | `signin_page` → signin.html.j2 | account |
| any unknown page | `_not_found` → `not_found_page` | add (serve.py error pages) |
| stale tab (403) | `STALE` literal in serve.py | add (serve.py error pages) |
| back office (`BACK_OFFICE_ROUTE`, and POSTs) | backoffice.html.j2 | out of scope |
| many public 404s (`/weekly`, `/parasha`, cycles, `/connect` shut, legal shut, …) | `_send(404, b"not found", "text/plain")`, **plain text, not the designed 404** | add? Worth one decision: a stranger on a dead weekly/parasha link sees the bare words "not found". |

Not routes: print.html.j2 (CLI export only). JSON routes (`/job/`, `/jobs`, `/readers`, …) carry error strings but are not pages.
