# Defect log — QA pass of 2026-10-11

Every confirmed defect, with what happened to it. Branch `qa-audit-2026-10-11`; each fix is
its own `fix(qa): QA-NNN` commit, followed by a `test(qa)` commit for its regression test
where one was written.

Three IDs are used. **QA-NNN** is a fix as committed. **ACCOUNT-**, **DESK-** and
**READER-** are the area testers' findings. The full reproduction for each, with steps,
conditions and console output, is in the area reports kept with the screenshots in the
private vault (see [README](README.md#evidence)). Library content shows in many of those
screenshots, which is why they are not in this public repository.

Severity: **Critical** = data loss, access control, or a core journey unusable · **High** =
a major feature or a common device blocked · **Medium** = a real usability or correctness
problem with a workaround · **Low** = polish.

Status: **Fixed** = changed and retested in the original failing conditions · **Open** = not
changed, with the reason · **Decision** = waits on a product call (see
[decisions](decisions.md)).

## Fixed (20)

| QA | Found as | Sev. | What was wrong | Where it was fixed | Regression test | Retest |
|---|---|---|---|---|---|---|
| QA-001 | lead sweep, DESK (header) | Medium | The desk header ran past the window at 737–793px (signed out) and 737–840px on every desk page in Russian: iPad portrait scrolled sideways, account off-screen | `chrome.css`: two rows below 56rem | `test_pages_browser::test_the_header_never_runs_past_a_tablet` (replaced the old "one line at 768px" test, whose premise was false) | Continuous resize 300→1300px, EN/RU/Aramaic menu, Chromium: no overflow |
| QA-002 | lead sweep | Medium | Onboarding in Russian at 320px pushed Aramaic's greeting off its card; three columns overflowed at 650–672px; no side gutter at 41–64rem | `arrival.css` | `test_the_languages_fit_in_russian[320,360,660,768,900]` | 320/660/768/1440 screenshots |
| QA-003 | lead sweep | Medium | Front door overflowed a 320px phone (9px EN; 19px RU from the try-a-link field); `/connect` in Russian by 24px | `landing.css`, `landing-classic.css` | — (CSS only) | Mobile emulation 320–430px, all public pages: no overflow |
| QA-004 | lead journey, DESK-01 | Medium | Android back / browser Back on onboarding left `/welcome` and lost every answer | `arrival.js`: a history entry per step | `test_the_phones_back_gesture_steps_back_through_the_arrival` | Chromium + WebKit, back/forward/page Back |
| QA-005 | lead (reach probe), READER-04 | Medium | The reader's way home (the mark) was 13×17px under a thumb; the shared "both ways" reach was flush to one side, so copy, hear, pager links, the grab and Keep reached 44px on one side only | `shared.css` | `test_reader_browser::test_the_way_home_answers_a_thumb_over_44px` | Hit-tested at 390 |
| QA-006 | ACCOUNT-01 | **High** | `/chat` on a phone squeezed the conversation to a 32px strip (209px at 1440): the footer stood inside the one-screen grid | `chat.css`, `chat.js` | extended `test_the_box_stays_in_view_however_long_the_thread` | 390/768/1440: thread 354/619/548px |
| QA-007 | ACCOUNT-02 | Medium | Russian pages showed English that `ru.json` had: /you's "Learning" and levels, chat's WORD/MEANING, the arrival's kinds (46 keys), home, words, add, connect | `builder.py`: a page carries every key its own scripts call | `test_strings::test_every_sentence_a_desk_script_asks_for_rides_with_the_page` | Live audit of 17 pages: 0 missing |
| QA-008 | ACCOUNT-03, ACCOUNT-06 | Medium | `/account/signin?lang=ru` answered refusals in English; the Russian `/add` no-key banner was English | `serve.py` | `test_hosted::test_a_refusal_is_said_in_the_language_of_the_page_it_was_asked_from` | — |
| QA-009 | ACCOUNT-04, DESK-08 (drawer) | Medium | Escape typed in the AI Assistant did nothing; opening left focus on `<body>`; closing did too; no dialog role | `talk.js`, `chat.js`, `_nav.html.j2`, `reader.html.j2` | `test_the_drawer_takes_the_keyboard_in_and_gives_it_back` | Chromium, WebKit, Firefox |
| QA-010 | READER-01 | Medium | A Library card showed a raw error with a filesystem path ("Looked in /Users/…/dialogues"), then "paste its text here" on a card with nowhere to paste | `dialogue/index.py`, `ingest/fetch/video.py`, `serve.py`, strings | `test_durable::test_a_text_missing_from_the_shelf_names_no_path_and_offers_no_paste` | Pressed live: "We can't open this one right now. Try another for now." |
| QA-011 | DESK-01 | Medium | Reloading on onboarding's last step went home, and the level was never asked | `arrival.js`: an unfinished arrival is resumed in this tab | extended QA-004 test (reload) | Chromium |
| QA-012 | DESK-04 | **High** | Library "See all" was 386px wide (EN) / 436px (RU) on phones; page and bottom bar slid sideways. Its menus then opened off-screen | `library.css`: row wraps; menus are sheets on a phone | `test_see_all_fits_a_phone_and_its_menus_come_up_as_sheets` | 320–390 EN/RU |
| QA-013 | DESK-06 | Medium | Bell and find were 30px wide under a thumb; the avatar's reach was clipped by `overflow: hidden` | `chrome.css` | extended `test_a_signed_in_header_fits_a_phone` | 320/390/768 hit-test; header fit 320–900 |
| QA-014 | DESK-08 | Medium | Escape from search or the account panel dropped focus on `<body>` | `palette.js`, `account.js` | `test_find_and_the_account_give_the_keyboard_back_on_escape` | Chromium, WebKit |
| QA-015 | ACCOUNT-11 | Medium | A stranger's 404 wore the signed-in desk (tabs, bell, assistant) and fired 401/403 | `builder.py`, `missing.html.j2`, `serve.py` | `test_hosted::test_a_strangers_404_is_the_doors_page_and_asks_for_nothing` | No failed requests |
| QA-016 | ACCOUNT-05 | Medium | With nothing new to make, `/add` said "Press Upload and we'll look for it" under a disabled Upload | `add.js` | `test_with_nothing_new_to_make_the_line_under_the_box_does_not_say_press_upload` | — |
| QA-017 | ACCOUNT-07 | Medium | `/you` at 320px: labels a word a line; in Russian the address switch drawn over its text | `you.css` | — (CSS only) | 320 RU, 390 EN screenshots |
| QA-018 | ACCOUNT-13 | Medium | Export promised everything and left out address, subjects, declared level, the record switch and the correction grant | `accounts.py` | `test_backup::test_the_export_carries_what_the_reader_set` | — |
| QA-019 | READER-02 | Medium | A refused Library press stayed at the head of Continue as "getting ready" for good, a card per press | `shelf.js` | `test_yours_js::test_a_refused_build_is_not_a_building_row` | — |
| QA-020 | DESK-03 | Medium | "One to try next" suggested the text Continue already showed | `home.js` | — (verified live) | Suggests Ruth, not the open article |

**Reaches users on deploy.** Readers bake their CSS and JS when built, and `deploy.sh` rewrites
every reader. Until a deploy, QA-005's reader half is visible only on newly built texts.

## Open — Medium

| ID | What | Why it is open | Recommendation |
|---|---|---|---|
| READER-03 | Offline, an unsaved page shows the browser's error page unless `/you/saved` was ever opened online | Keeping `/you/saved` on first save broke five `test_offline_browser` tests that encode design.md §12 "A worker keeps what the reader saved, and fetches nothing else", and the extra index entry changed eviction. Reverted. | Decision D4 |
| READER-04 (rest) | Under 44px on touch, drawn and not reached: parasha scrubber 37×14, video play 28×28, the card's × half under the grab, "Add your meaning" 19px tall | Each needs its own layout change in the reader's strip; built readers are static files, so each is visible only after a rebuild | Same treatment as QA-005; strip on two rows on a phone (also READER-05) |
| READER-06 | Contents page says "You know 0%" while the reader says 25% | The server counts marked words only; the reader also counts words assumed known from the declared level. There is no server-side version of that assumption | Decision D5 |
| DESK-10 | Your Words shows no meaning for words claimed from "Words you may already know" | The list reads meanings only from the browser's own store; needs server or store work | Keep the gloss the claim table showed when a word joins the list |
| DESK-11 | "ignore" removes a word with no undo and no Ignored view | Product behaviour | Decision D6 |
| — | A signed-out deep link (an expired session, a bookmark) lands on "COMING SOON" and does not return to the page after sign-in | Touches sign-in redirects (an open-redirect risk to design carefully) | Decision D2 |

## Open — Low

READER-05 (phone player clock clipped, scrubber 37px), READER-07 (first Escape after a stage
press does not close the card), READER-08 (a score "72-73" breaks at its hyphen — content
bidi), READER-09 (credits line overlaps the pager at 390×844 on a chapter's last page),
READER-10 (desktop word card can cover the bar), READER-11 (an unready video part says "too
long" — wording produced by `--max-cost 0`; each visit adds a job row), READER-12 (card × can
scroll away), READER-13 (old weekly build says "targum — Learn" — fixed in the template,
rebuild needed), READER-14 (news article called "Book" on its contents page), READER-15
(listening view says "Chapter 2 of 7" where the parasha says aliyah names).
DESK-02 (no way back to English after pressing RU in onboarding), DESK-05 (RU 320 See-all
row facts overlap), DESK-07 (other small targets: Tanakh-map cells 7×7, sort heads 20px,
playlist sheet × 40px, `/words` export links 21px), DESK-09 (phone sheets do not lock page
scroll), DESK-12 (one-week Progress chart is an unlabelled slab), DESK-13 (Tanakh map book
names English in Russian), DESK-14 (subscribe confirm page copy).
ACCOUNT-08 (a Record clip is called a video: `.webm` classed by extension), ACCOUNT-09 (a
0-byte file accepted as "1 KB"), ACCOUNT-10 (signed in, `/account/signin` still shows the
form), ACCOUNT-12 (`/library/<unknown>` is bare text "not found"), ACCOUNT-14 (back-office
per-account table scrolls the page sideways — admin only), ACCOUNT-15 (empty Chat History
is a blank sheet), ACCOUNT-16 (offline pages show "Sign in" to a signed-in reader),
ACCOUNT-17 (after deleting, the closing message flashes for 1.5s and the front page follows),
ACCOUNT-18 (smaller notes: expired-link page shell differs from sign-in; `/account/me` 403
HTML vs JSON 401; RU chat placeholder wording; OAuth approve page breaks the address
mid-word).
Lead: signed-out series pages (weekly, parasha, daily cycles) carry the desk's scripts,
which ask for `/jobs`, `/chat/list` and `/account/me` and are refused (401/403 in the
console; nothing shown to the reader). In WebKit, home's redirect for an account that
never finished the arrival cancels fetches in flight, and WebKit reports each as an
unhandled rejection (`access control check`); nothing is shown to the reader.
Lead: the reader's home link in readers built before 2026-10-08 says "targum — Learn"
(stale build; fixed by the next rebuild); the desk's focus ring is gold `#b8935e`, measured
2.31:1 on the desk ground (Decision D3).

## Not defects (checked and ruled out)

- **WebKit "Refused to apply a stylesheet" on every page.** Playwright's WebKit injects a
  style for screenshots, which the page's hash-pinned CSP refuses. It appears only while a
  screenshot is taken; pages loaded without one log nothing.
- **"Continue on /welcome was ink on teal"** (desk tester, early in the run). Not reproduced
  on the final build.
- **Signed-out series pages carry the desk's bar.** design.md §12, "A series is one page of
  the desk, for everyone", 2026-10-09.
