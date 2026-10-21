# Coverage matrix — QA pass of 2026-10-11

Three parts. **A** is the automated sweep of every route a person reaches, on the final
build, cell by cell. **B** covers the journeys, done by hand or by script, by area; these
are the area testers' own tables, copied as written. Evidence names in **B** refer to
screenshots in the private vault (see [README](README.md#evidence)). **C** is what was
not tested.

Phones are emulated (Chromium with `is_mobile`, touch, DPR 2; Firefox has no mobile mode,
so its phone sizes are a desktop window at that width). WebKit is desktop WebKit, an
approximation of Safari. None of it is a physical device.

## A · Sweep of the final build

Each cell is one page load, checked for:
- a status that is not 2xx where 2xx was expected
- horizontal scroll (the document wider than the viewport)
- a page error
- **after fixes**: the same checks repeated once the fixes had landed

`✓` = loaded with no horizontal scroll and no page error. `404 ✓` = the designed 404 page,
as intended. Before the fixes, 27 of the 324 public loads scrolled sideways; after them,
none of the 704 loads did.

Interface language is English unless the route says `-ru`. The signed-in sweep used a
synthetic account that had opened two texts.

### Signed out — 27 routes × 4 viewports × 3 engines

| route | path | ch 320x568 | ch 390x844 | ch 768x1024 | ch 1440x900 | we 320x568 | we 390x844 | we 768x1024 | we 1440x900 | fi 320x568 | fi 390x844 | fi 768x1024 | fi 1440x900 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| landing | `/` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| landing-ru | `/?lang=ru` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| how | `/how` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| how-ru | `/how?lang=ru` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| about | `/about` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| connect | `/connect` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| connect-ru | `/connect?lang=ru` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| shelf | `/library` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| shelf-ru | `/library?lang=ru` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text-jonah | `/library/jonah` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text-scene | `/library/scene-30-the-pizza` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text-onkelos | `/library/onkelos-genesis` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text-khan | `/library/ka-absolute-value-inequalities` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text-italian | `/library/mmm-ma-dai-boh` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| privacy | `/privacy` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| terms | `/terms` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| signin | `/account/signin` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| signin-ru | `/account/signin?lang=ru` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| weekly | `/weekly/2026-w39/bet` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| parasha | `/parasha` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| parasha-one | `/parasha/bereshit` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| mishna-yomi | `/mishna-yomi` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| tehillim | `/tehillim` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 404 | `/nope` | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ |
| enter-bad | `/account/enter?t=bad` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| waitlist-bad | `/waitlist/confirm?t=bad` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| holding-you | `/you` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Signed in — 20 routes × 15 viewports, Chromium

| route | path | ch 320x568 | ch 360x640 | ch 375x667 | ch 390x844 | ch 412x915 | ch 667x375 | ch 844x390 | ch 768x1024 | ch 820x1180 | ch 1024x768 | ch 1280x720 | ch 1366x768 | ch 1440x900 | ch 1920x1080 | ch 2560x1440 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| home | `/` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| library | `/library` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| progress | `/progress` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| words | `/words` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| phrases | `/phrases` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| add | `/add` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| you | `/you` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| saved | `/you/saved` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| playlists | `/playlists` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| tanakh | `/tanakh-map` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| chat | `/chat` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| subscribe | `/subscribe?kind=series&key=parasha` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| connect-desk | `/connect` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ruth-contents | `/reader/<text>/reader/index.html` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ruth-1 | `/reader/<text>/reader/sec-0001.html` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| parasha-reader | `/parasha/read/noach/reader/sec-0001.html` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| weekly-reader | `/weekly/read/weekly-2026-w39-bet-he/reader/index.html` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| daily-reader | `/mishna-yomi/read/2026-10-11/reader/index.html` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 404-in | `/nope` | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ |
| parasha-in | `/parasha/noach` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Signed in — 20 routes × 4 viewports, WebKit

| route | path | we 320x568 | we 390x844 | we 768x1024 | we 1440x900 |
|---|---|---|---|---|---|
| home | `/` | ✓ | ✓ | ✓ | ✓ |
| library | `/library` | ✓ | ✓ | ✓ | ✓ |
| progress | `/progress` | ✓ | ✓ | ✓ | ✓ |
| words | `/words` | ✓ | ✓ | ✓ | ✓ |
| phrases | `/phrases` | ✓ | ✓ | ✓ | ✓ |
| add | `/add` | ✓ | ✓ | ✓ | ✓ |
| you | `/you` | ✓ | ✓ | ✓ | ✓ |
| saved | `/you/saved` | ✓ | ✓ | ✓ | ✓ |
| playlists | `/playlists` | ✓ | ✓ | ✓ | ✓ |
| tanakh | `/tanakh-map` | ✓ | ✓ | ✓ | ✓ |
| chat | `/chat` | ✓ | ✓ | ✓ | ✓ |
| subscribe | `/subscribe?kind=series&key=parasha` | ✓ | ✓ | ✓ | ✓ |
| connect-desk | `/connect` | ✓ | ✓ | ✓ | ✓ |
| ruth-contents | `/reader/<text>/reader/index.html` | ✓ | ✓ | ✓ | ✓ |
| ruth-1 | `/reader/<text>/reader/sec-0001.html` | ✓ | ✓ | ✓ | ✓ |
| parasha-reader | `/parasha/read/noach/reader/sec-0001.html` | ✓ | ✓ | ✓ | ✓ |
| weekly-reader | `/weekly/read/weekly-2026-w39-bet-he/reader/index.html` | ✓ | ✓ | ✓ | ✓ |
| daily-reader | `/mishna-yomi/read/2026-10-11/reader/index.html` | ✓ | ✓ | ✓ | ✓ |
| 404-in | `/nope` | 404 ✓ | 404 ✓ | 404 ✓ | 404 ✓ |
| parasha-in | `/parasha/noach` | ✓ | ✓ | ✓ | ✓ |

Also swept continuously, from 300 to 1300px in 10px steps, on the final build: `/`,
`/?lang=ru`, `/connect?lang=ru`, `/library`, `/parasha`, `/welcome`, `/you`, the 404, and
the signed-in desk in English, in Russian, and with the Aramaic language menu. No width
scrolled sideways.

The JSON-only routes (`/readers`, `/jobs`, `/job/<id>`, `/search.json`, `/account/*`,
`/chat/*`, `/playlists*.json`, `/subscriptions*.json`, `/offline.json`, `/voice`, `/sync`,
`/events`, `/gloss`, `/build`, `/prepare`, `/describe`, `/upload/*`, `/oauth/*`, `/mcp`,
`/.well-known/*`) were exercised through the pages that call them in **B**. Their failures
were watched in the console and in the network log.

## B · Journeys, by area

### Sign-in, Upload, the AI Assistant, the bell, account, connector, back office

| route/feature | state | viewport(s) | engine(s) | language | result | evidence |
|---|---|---|---|---|---|---|
| /account/signin render | signed out | 390, 1440 | Chromium, WebKit, Firefox(1440) | EN, RU | pass | signin-en-390, signin-ru-1440, webkit-signin-390 |
| sign-in submit → mail → enter → press | invited account | 390, 1440 | Chromium, WebKit, Firefox | EN | pass (lands /welcome) | signin-sent-390, enter-page-390 |
| empty / `not-an-email` | | 390 | Chromium | EN | pass (native validation) | |
| `a@b` | | 390 | Chromium | EN / RU | pass EN / fail RU | ACCOUNT-03 |
| not invited address | | 390 | Chromium | EN / RU | pass EN / fail RU | ACCOUNT-03 |
| double-submit | | 390 | Chromium | EN | pass (1 mail) | |
| rate limit (6th ask) | | 390 | Chromium | EN / RU | pass EN / fail RU | ACCOUNT-03 |
| used link, garbage token, no token | signed out / in | 390 | Chromium | EN | pass / Low | ACCOUNT-10, 18 |
| /account/signin while signed in | signed in | 390, 1440 | Chromium | EN | fail (Low) | ACCOUNT-10 |
| stale cookie on desk pages | edited cookie | 390 | Chromium | EN | pass (holding page, no data) | stale-cookie-you-390 |
| stale cookie on JSON | edited cookie | – | Chromium | – | pass (no data), inconsistent codes | ACCOUNT-18 |
| waitlist form on / | signed out | 390 | Chromium | EN | pass | waitlist-submitted-390 |
| waitlist confirm link (twice) | | 390 | Chromium | EN | pass | waitlist-confirm-*, waitlist-confirmed-0 |
| /waitlist/stop (with/without token) | | 390 | Chromium | EN | pass (deliberately the same answer) | waitlist-stop-* |
| 404s /nope /you/nope /build/nope /set/nope /reader/… | in / out | 390 | Chromium | EN | pass in; fail out | ACCOUNT-11 |
| /library/nope | in / out | 390, 1440 | Chromium | EN | fail (Low) | ACCOUNT-12 |
| another account's /build /set /chat ids, POST press | qa-make | 390 | Chromium | EN | pass (404) | `acl.py` |
| /add paste: YouTube, article, garbage, ftp, plain URL, Hebrew, description | no key | 390 | Chromium (+WebKit, FF spot) | EN, RU | fail (copy) | ACCOUNT-05 |
| /add files: txt, pdf, png, 0-byte, 60MB sparse mp4, exe, two files, remove × | no key | 390, 1440 | Chromium | EN | partial (press blocked) | ACCOUNT-09 |
| /add Record | mic granted / denied | 390, 1440 | Chromium (fake device) | EN | grant works, wrong label; deny message clear | ACCOUNT-08, add-record-deny-390 |
| /add no-key banner | $0 | 390, 320 | Chromium, WebKit, FF | EN, RU | fail (RU English) | ACCOUNT-06 |
| AI Assistant open/close (pill, ×, grab, Esc) | qa-make | 390, 1440 | Chromium, WebKit, FF | EN, RU | partial | ACCOUNT-04 |
| Send with no key (Enter) | | 390, 1440 | Chromium | EN | pass ("We can't answer right now." standing, text kept) | chat-sent-nokey-* |
| Chat History | no chats | 390, 1440 | Chromium | EN, RU | Low | ACCOUNT-15 |
| drawer across navigation | | 390, 1440 | Chromium | EN | as designed (§12) | chat-restored-* |
| /chat page | | 390, 768, 1440 | Chromium | EN, RU | fail | ACCOUNT-01 |
| bell open/Esc/outside/toggle, empty state | | 390, 1440 | Chromium | EN, RU | pass | bell-open-*, ru-bell-320 |
| /you sections render | | 390, 1440, 320 | Chromium, WebKit, FF | EN, RU | fail at 320 | ACCOUNT-07 |
| /you address, level, start French (persist on reload) | qa-acct | 390 | Chromium | EN | pass | you-after-start-french-390 |
| /you read-into Russian and back | qa-make | 320/390 | Chromium | RU | pass (switch), strings partial | ACCOUNT-02 |
| plan/credits display | | 390, 1440 | Chromium | EN | pass (buttons disabled, "Payments open soon") | you-390 |
| /you/saved | | 390, 1440, offline | Chromium | EN | pass; offline header Low | ACCOUNT-16 |
| Export download + JSON | | 390, 1440 | Chromium | EN | pass (download), fail (completeness) | ACCOUNT-13 |
| Sign out, session gone, back x2, old cookie replay | qa-acct; qa-out2 | 390 | Chromium; WebKit | EN | pass (no private data on back, localStorage empty, export 401) | signout-back1-390, webkit-signout-back-390 |
| Delete account (two-press, after) | qa-del1 | 390 | Chromium | EN | pass; landing Low | ACCOUNT-17 |
| /connect | out / in | 390, 1440 | Chromium | EN | pass | connect-out-*, connect-in-* |
| /oauth/authorize missing/garbage/wrong redirect/plain PKCE | | 390 | Chromium | EN | pass (clear 400 page) | oauth-garbage-390 |
| /oauth/register + approve page, Not now, Connect (303 with code+state) | synthetic client | 390, 1440 | Chromium | EN | pass | oauth-approve-* |
| approve while signed out | | 390 | Chromium | EN | pass ("Sign in to finish connecting…") | oauth-approve-signedout-390 |
| /back-office non-admin | | 390, 1440 | Chromium | EN | pass (404) | |
| /back-office admin (look only) | qa-admin1 | 390, 1440 | Chromium | EN | fail (overflow, Low) | ACCOUNT-14 |
| Russian walk: /add, /you, drawer, bell, /chat, saved, 404, connect | qa-make | 320 | Chromium | RU | partial | ACCOUNT-02, 06, 07 |

### Onboarding, Home, Library, series, Progress, Your Words, playlists, subscriptions

| route/feature | state | viewport(s) | engine(s) | language | result | evidence |
|---|---|---|---|---|---|---|
| /welcome steps 1–3, Continue, Back (in-page and chevron) | new account | 390, 320, 844×390, 1440 | Chromium | EN | pass | ob-01…ob-11 |
| /welcome browser back, forward, reload per step | new | 390 | Chromium | EN | **fail** DESK-01 | ob-03, ob-06 |
| /welcome EN · RU switch | new | 390, 320 | Chromium | EN→RU | **fail** DESK-01/02 | ob-20…ob-25 |
| /welcome Russian text, 320 overflow, sticky Continue | new | 320, 375, 844×390 | Chromium | RU | pass on the final build | ob-24, ob-25 |
| /welcome "I'm not sure, show me a page" | new (writes blocked) | 390 | Chromium | EN | pass (opens the Hapoel Holon article) | ob3 log |
| /welcome finish per language (he, ru, fr, it, arc, yi) | new (writes blocked) | 390 | Chromium | EN | pass (he opens a text; the others go home, nothing to open in the scratch library) | ob3 log |
| /welcome keyboard (Tab order, focus ring, Enter) | new | 1440 | Chromium | EN | pass (radios use Tab, not arrows; minor) | ob5 log |
| /welcome real completion | → done | 390 | Chromium | EN | pass (opened the reader; Back → /) | ob-30 |
| Home brand-new (One to start with: Ruth) | new | 320, 390, 1440 | Chromium | EN | pass | home-00-brandnew-* |
| Home after activity, Continue + One to try next | active | 390, 1440 | Chromium | EN | **fail** DESK-03 | kb-lang-after-esc-1440 |
| Home tabs Recent / Playlists / Subscriptions / Uploads, ?show= | active | 390 | Chromium | EN | pass (back note in DESK-15) | home-tab-* |
| Row ⋯ menu (tap; outside click; Esc) | active | 390, 1440 | Chromium | EN | pass | home-rowmenu-open-390 |
| Trash / restore | — | — | — | — | blocked: needs an upload of your own; a $0 build cannot make one | — |
| Top bar, active place per page | active | 390, 1440 | Chromium | EN | pass except /words, /phrases, /you (DESK-15) | chrome1 log |
| Account sheet / panel (open, Esc, outside, back) | active | 390, 1440 | Chromium | EN | pass; scroll lock DESK-09, focus DESK-08 | chrome-account-* |
| Language sheet (lists languages, Esc) | active | 390, 1440 | Chromium | EN | pass | chrome-lang-* |
| Bell panel ("Nothing new.") | active | 390, 1440 | Chromium | EN | pass | chrome-bell-* |
| Search palette (⌘K, Ctrl+K, /, button, phone row) | active | 390, 1440 | Chromium | EN | pass; focus return DESK-08 | chrome-palette-* |
| AI Assistant pill / drawer open–close, covering content | active | 390, 1440 | Chromium | EN | pass (no content left under the pill at page end) | chrome-talk-*, cover-bottom-* |
| Header overflow sweep 600→1100 in 10px steps | active | 600–1100 | Chromium | EN, RU, with Italian chosen | pass: no overflow or overlap at any width. Phone bar ≤640; two rows 650–890; one row ≥900 (bar 71→73px tall as the rem grows) | header.py, header-ru-*, header-it-* |
| Tablet 768×1024, 1024×768 | active | 768, 1024 | Chromium | EN | pass except the 44px items (DESK-06/07) | tab-* |
| /library search: he with and without vowels, translit, English, none, Enter, blank | active | 1440 | Chromium | EN | pass (24/24, 14/14, 2, 0 with a clear empty state) | lib-search-* |
| /library doors, See all, Kind / Level / Language menus | active | 1440, 768, 1024 | Chromium | EN | pass | lib-seeall-1440 |
| /library See all | active | 320, 360, 375 | Chromium | EN | **fail** DESK-04 | see-stretch-en-320-b |
| /library See all | active | 320, 390 | Chromium | RU | **fail** DESK-04/05 | see-stretch-ru-320 |
| /tanakh-map | active | 390, 1440, 768, 1024 | Chromium | EN | pass at desktop; phone cells DESK-07 | s1-tanakh-map-* |
| /parasha, /parasha/vayera, /parasha/noach, /parasha/bad | active | 390 | Chromium | EN | pass; bad = bare 404 | series_parasha* |
| /weekly → /weekly/2026-w39/aleph | active | 390, 1440 | Chromium | EN | pass ("This week" note) | series_weekly-390 |
| /mishna-yomi | active | 390, 1440 | Chromium | EN | pass | series_mishna-yomi-390 |
| /subscribe confirm: none, series ×2, bad series, channel, podcast, topic, bogus | active | 390 | Chromium | EN | pass apart from copy (DESK-14) | subscribe_* |
| Subscribe to the Weekly (free) → /subscriptions/120; Back shows "already"; series page shows Subscribed | active | 390 | Chromium | EN | pass | sub-after-press-390 |
| Subscriptions tab with one subscription | active | 390 | Chromium | EN | pass | sub-tab-390 |
| /progress after activity | active | 320, 390, 1440 | Chromium | EN | pass layout; chart DESK-12 | progress-* |
| /progress empty account | — | — | — | — | not captured before activity (the account had words by the time I reached it) | — |
| Touchstone ladder | active | 390 | Chromium | EN | not shown: "We'll show which kinds… once we've measured the library's texts" (scratch library unmeasured) | progress-320 |
| /words table (desktop) and list (phone): filters, find, none-found, stage change + reload, ignore, claim known ×2 (104 words) | active | 390, 1440 | Chromium | EN | stage and filters pass; DESK-10, DESK-11 | words-* |
| Practice card | — | 390, 1440 | — | — | not shown: `/account/words` has `practise: []` (no finished section) | — |
| /phrases | empty | 390, 1440 | Chromium | EN | pass (empty state) | s1-phrases-* |
| /playlists: new playlist (emoji, HTML, long name), ?add=&title= sheet, add, /playlists/4, back, bogus id | active | 390 | Chromium | EN | pass; notes DESK-07/15 | pl-* |
| Russian interface: home, tabs, library, see-all, progress, words, phrases, playlists, playlist, subscription, parasha, weekly, mishna, tanakh-map, you, subscribe | reads = ru | 320, 390 | Chromium | RU | pass (only names and credits left in English) except DESK-04/05/13 | ru_* |
| Second learning language (Italian), every desk page follows the menu | he + it | 390 | Chromium | EN | pass (playlists and subscriptions list across languages; product question) | l2-* |
| Switch back to Hebrew from /library | he + it | 1440 | Chromium | EN | pass; the account keeps `language: he` | back.py |
| WebKit: home, library, see-all, progress, words | active | 390, 1440 | WebKit | EN | pass (no see-all overflow in WebKit) | wk-* |
| Firefox desktop: home, library, see-all, progress, words, playlist, subscription | active | 1440 | Firefox | EN | pass | ff-* |

WebKit logs "Refused to apply a stylesheet … style-src" on every page in my sweep. Every `<style>` on the page hashes to a value in the CSP, and the sweep takes screenshots, so this is Playwright's injected screenshot style (the reader agent reached the same conclusion). Not logged as a defect.

### The reader

| route/feature | state | viewport(s) | engine(s) | language | result | evidence |
|---|---|---|---|---|---|---|
| /welcome → first reader | new account | 390×844 | Chromium | EN | pass | onboard-*.png |
| Library card press (story) | $0 budget | 390×844 | Chromium | EN | fail READER-02 | lib-story-pressed-390*.png |
| Library card press (dialogue/video) | catalogue item missing | 390×844 | Chromium | EN | fail READER-01 | lib-dialogue-path-leak-390*.png |
| Home Continue → reader at chapter/page | signed in | 390×844 | Chromium | EN | pass (+READER-02 cards) | continue-landing-390.png, home-continue-blocked-390.png |
| /r/<code>, /open/<id>, /reader/<f>/reader/<p> | signed in / out | 390×844 | Chromium | EN | pass | doors.py output |
| Modern prose reader (Holon) | current build | 320, 390, 412, 768, 1024, 1280, 1440, 2560 | Chromium | EN | pass with READER-04/08/10 | holon-*.png |
| Tanakh with taamim (Noach, Ruth) | current | 390, 1440 | Chromium, WebKit, Firefox | EN | pass | noach-s1-390.png, core-playing-*.png |
| Aramaic (Daniel 2) | rebuilt | 390, 1440 | Chromium | EN | pass | kind-daniel2-390.png, aramaic-daniel-card-1440.png |
| Dialogue (מה השעה) | rebuilt | 390 | Chromium | EN | pass (no audio in this build) | kind-dialogue-390.png |
| Video (beside, theatre, divider, next part) | rebuilt sidecar | 390, 1440 | Chromium | EN | pass with READER-04/11 | video-*.png |
| Audio (parasha leyning): play/pause/speed | current | 390, 1440 | Chromium, WebKit, Firefox | EN | pass with READER-05 | core-playing-*.png |
| Listening view, Up next | current | 390×844 | Chromium | EN | pass with READER-15 | listen-*.png |
| Russian / Italian LTR reader | rebuilt | 390 | Chromium | EN UI | pass | kind-ru-390.png, kind-it-390.png |
| Contents page + Continue at chapter | current | 390, 1440 | Chromium | EN | fail READER-06/14 | fresh-index-390.png |
| Word card stages / own meaning / Ask refusal | signed in | 390, 320, 390×450, 844×390, 1280, 1440 | Chromium, WebKit, Firefox | EN | pass with READER-04/07/10/12 | wordcard-*.png |
| Phrase pick | desk drag / phone touch | 1440, 390 | Chromium | EN | pass with READER-04 | phrase-*.png |
| Kept-words list (column vs sheet) | — | 390, 1280 | Chromium | EN | pass | list-sheet-390.png, desk-list-chromium-1280x720.png |
| Aa, ⋯ menus, sheets, rotate | — | 390, 320, 844×390, 1440 | Chromium, WebKit, Firefox | EN | pass | more-*.png, rotate-*.png, core-aa-*.png |
| Add to playlist sheet | new playlist | 390 | Chromium | EN | pass | playlist-*.png |
| Hear this section | $0 | 390 | Chromium | EN | pass (refusal "We can't read aloud right now.") | more-hear-section-refusal-390.png |
| End of a part card | — | 390 | Chromium | EN | pass with READER-09 | endpart-*.png |
| Save for offline, offline reload | saved / unsaved | 390 | Chromium | EN | fail READER-03 | offline-*.png |
| Keys, Tab order, focus ring | — | 1280, 1440 | Chromium | EN | pass with READER-07 | desk-keys-*.png, tab-*.png |
| Weekly reader | stale build by design | 390 | Chromium | EN | READER-13 | weekly-390.png |
| Persistence (stage, page, phrase) | reload / fresh context | 390, 1440 | Chromium, WebKit, Firefox | EN | pass | persist.py output |

## C · Not tested

### Account area

- Any real build, a priced card, or the `/build/<id>` and `/set/<id>` press pages: with $0 and no key, Upload stays disabled, so no job of qa-make's exists to open. Other accounts' ids correctly 404.
- Upload size limits on the server (MAX_UPLOAD 32MB; chunked video): blocked behind the disabled Upload.
- A connection listed on `/you` with Disconnect: I did not exchange the code for a token, so nothing is listed.
- Events/notification toggles and Telegram: hidden in this environment (`record-switch`, `telegram-go` exist but the sections are not shown), so their visible behaviour was not testable.
- Real iOS/Android: emulation and desktop WebKit only. The mic test used Chromium's fake device.
- Touch-target sizes: early measurements taken mid-load showed 36–42px heights, but at steady state the registered controls measured 44px tall, so no target-size defect is logged. Widths below 44 remain on the bell (30px), avatar (36px reach) and Saved's "3/5/10" segments (36px). Whether §8 means both axes is for the owner.

### Desk area

- Trash and restore on Home: there is nothing of my own to delete, and a $0 server cannot build an upload.
- The practice card: it needs a finished section (the reader's area).
- Progress for a brand-new account: the account already had words when I reached the page.
- Real iOS and Android: emulation only.
- Confirming a paid subscription cap: told not to.

### Reader area

- **Russian interface in the reader.** The UI language follows what the account reads (`_ui_language`), and the reader bakes its strings at build time. `/parasha/read/noach/reader-ru/sec-0001.html` returns 404 (it is served some other way), and changing this account's languages would disturb the other checks. This should be tested with an account that reads Russian.
- **The placement reader from /welcome "I'm not sure".** The account was already onboarded, and the welcome area belongs to another agent.
- **Audio output, the lock screen and Media Session.** These are headless. Only control state was checked.
- **A real on-screen keyboard and native long-press selection.** I approximated them with short viewports and a scripted selection after a touch `pointerdown`.
- **Firefox mobile.** Playwright's Firefox has no `is_mobile`.
- **Video in WebKit.** I ran the core journey in WebKit on the parasha audio and the article, not on the video sidecar.
- **The audiobook (מסעות בנימין השלישי) player.** This copy has no recording in its build. Audio was covered by the parasha.

### Across the pass

- No physical iPhone or Android phone. Not covered: the real keyboard, URL-bar resizing,
  notch insets, backgrounding a tab and coming back, the lock screen, native selection
  menus, and iOS storage eviction.
- Anything that spends: builds, translation, the assistant's answers, voice.
- Telegram and payments (switched off).
