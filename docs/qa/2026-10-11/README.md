# QA report — mobile browser and desktop, 2026-10-11

A full pass over targum in a running app, phone first and desk equally. Branch
`qa-audit-2026-10-11`, from master `9724e330`.

| File | What it holds |
|---|---|
| [defects.md](defects.md) | Every confirmed defect: fixed, open or waiting on a decision |
| [coverage.md](coverage.md) | Route × state × viewport × engine × language, with results |
| [decisions.md](decisions.md) | The calls only you can make, with a recommendation each |
| [mobile-app-notes.md](mobile-app-notes.md) | What this pass found that the app should do natively |

## Verdict

**Mobile browser: much closer, not yet ready.**
The two High defects found on phones are fixed: the Library's See all scrolled sideways,
and the `/chat` page showed a 32px strip. With them, every overflow found at 320–430px is
fixed, on every route swept. No Critical or High defect remains open.

What still stands between it and "ready" is one Medium on the come-back journey, a
signed-out deep link that says "COMING SOON" (D2). There are also four Medium gaps a phone
reader feels: offline fallback (D4), the reader's remaining small controls, the two "known"
figures that disagree (D5), and meanings missing from Your Words. Nothing here was run on a
real phone (see *Not tested*).

**Desktop: ready, with two caveats.**
Every route works at 1280–2560px in Chromium, WebKit and Firefox. Keyboard focus now enters
and leaves every overlay and returns to the key that opened it. The caveats: the focus ring
inside the product is gold, at 2.31:1 on the desk's ground, which fails WCAG 1.4.11 (D3).
And at 2560px the reader's Under view runs English at about 140 characters a line.

## What was tested

- **Every route** in the server's dispatch table, about 150, inventoried from `serve.py`
  and from the running app. The ones a person reaches were opened in a browser. The
  JSON-only routes were exercised through the pages that call them.
- **Five synthetic accounts plus throwaways**, all `@example.com`, on a scratch copy of the
  library and database. The server was the worktree's own, in hosted mode with the
  production switches on (front door, public shelves, connector, legal, parasha, daily),
  no API keys and a $0 budget. Nothing could spend. Mail went to a local sink, and no
  message left the laptop.
- **Automated sweeps** for horizontal overflow, controls under 44px on a coarse pointer
  (hit-tested, not just measured), console errors and failed requests:
  - 27 signed-out routes × 4 core viewports × Chromium, WebKit and Firefox
  - 20 signed-in routes × all 15 viewports of the brief in Chromium, plus the core four
    in WebKit
  - Repeated on the final build: 704 page loads, no horizontal scroll at any viewport in any
    engine, and no page that failed to load.
- **Continuous resizes** from 300 to 1300px in 10px steps, on the desk and the public
  pages, in English, Russian, and with the Aramaic language menu.
- **Journeys, by hand and by script**, at phone and desk sizes:
  - sign-in by mailed link (including used, garbage and rate-limited links)
  - onboarding, every step, with back, forward and reload
  - Home and Continue; Library search, doors, See all and its menus
  - series pages, subscribe, playlists, Progress, Your Words
  - the reader: word card, stages, phrases, menus, contents, listening, video beside and
    Theatre, the end of a part, save for offline
  - Upload with links, text, files and Record; the AI Assistant drawer and `/chat`
  - the bell; `/you`, export, sign-out, account deletion; the connector's OAuth pages;
    the back office as non-admin and admin
  - the waitlist from the front door to its confirm link
- **Russian interface** on every desk page, and the public pages under `?lang=ru`. Hebrew
  is a learning language, not an interface language, so RTL was tested as content: Hebrew,
  Aramaic and Yiddish texts, mixed numbers and punctuation, page arrows in each direction.
- **Keyboard**: tab order, visible focus, and Escape and focus return on every overlay.
- **Offline**: the service worker, saved texts, and an unsaved page while offline.
- **The test suite**: 6,903 tests plus the regression tests added here. ruff and mypy are
  clean.

## Highest-impact findings, all fixed

1. **`/chat` was unusable on a phone** (High, QA-006). The site's foot stood inside the
   one-screen grid, so the conversation was 32px tall.
2. **Library See all scrolled sideways on every phone** (High, QA-012). The bar of places
   slid off with it, and its menus opened off-screen.
3. **The desk header pushed past the window on tablets** (QA-001): iPad portrait in
   Russian on every desk page, and signed-out pages in English.
4. **Russian pages showed English that `ru.json` had** (QA-007). Fixed at the root: a page
   now carries every key its own scripts call, instead of thirty hand-kept prefix lists.
5. **Onboarding lost the reader's answers** on the back gesture and on reload, and could
   skip the level question entirely (QA-004, QA-011).
6. **A filesystem path was shown on a Library card** (QA-010).
7. **The AI Assistant drawer trapped Escape**, and three overlays dropped focus on
   `<body>` (QA-009, QA-014).
8. **Touch reach**: the way home from a reader was 13×17px. The shared reach rule reached
   one side only, and the header's bell and account were under 44px across (QA-005,
   QA-013).

Twenty fixes in all, one commit each, with 16 regression tests added or extended. The rest
of the Medium and Low items are listed in [defects.md](defects.md) with reasons.

## Not tested, and why

- **No physical device.** Every phone result is Chromium's mobile emulation (`is_mobile`,
  touch, DPR 2) or desktop WebKit at a phone size. Neither proves iOS Safari or Android
  Chrome behaviour. Untested for that reason: the real on-screen keyboard resizing the
  viewport, the URL bar growing and shrinking (`svh`/`dvh`), safe-area insets on a
  notched phone, native long-press selection and the copy menu, backgrounding a tab and
  coming back, the lock screen and media session, real rotation, and the iOS 7-day
  storage eviction.
- **Firefox on a phone**: Playwright's Firefox has no mobile mode. Firefox was run at
  desktop sizes.
- **Anything that spends**: builds, translation, the assistant's answers, voice. The $0
  budget was deliberate, so their refusal states were tested and their success paths
  were not.
- **The daily cycles' content and real audio output**: the laptop's copy has no daily
  corpus, and audio was checked by its controls and state, not by ear.
- **Trash and restore, the practice card, and a brand-new account's Progress**: these
  need an upload or a finished section, which a $0 server cannot make.
- **Telegram, payments (plans are off), and a listed connector connection with Disconnect.**
- **200% zoom** was covered by the 320px reflow sweeps, which are the equivalent width.
  Text-size settings were not tested: desk pages set the root size in px (`clamp(16px…)`),
  so a desktop browser's font-size preference does not reach them. Zoom does.

## Evidence

Screenshots (about 500), the three area testers' full reports and the sweep results are in
the private vault, under `Primary/Project Planning/Targum internal docs/QA 2026-10-11/`.
They are kept out of this repository because they show library content. The sweep and
probe scripts are kept there too.
