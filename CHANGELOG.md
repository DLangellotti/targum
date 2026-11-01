# Changelog

Notable changes to targum, newest first. Versions follow the 4-digit
`MAJOR.MINOR.PATCH.MICRO` in `pyproject.toml` and are tagged in git.

## [Unreleased]

### Fixed
- A word's card no longer follows a lemma the word does not spell (David, 2026-10-31).
  נשתיק, "we will silence", showed התקין "install; set up", root ת־ק־ן and "All forms of
  התקין": DICTA has no השתיק, and the annotator's letter check let every nun drop as if
  it had assimilated, so התקין's ת־ק passed. A page build, a rebuild and the occurrence
  counts now check each DICTA lemma again, letting a nun go only first in the root or
  before a suffix's ת (`annotate.lemma_check`). A refused verb takes the CC0 paradigm
  table's verb, with its root and binyan, where the word is a form of exactly one (נשתיק
  is השתיק's). Any other refused lemma becomes a gap, as the annotator does itself. Over
  the laptop's 212 grammar/8 texts this moves 116 of 89,035 verbs (about 54 to the table's
  verb), 132 nouns and 21 adjectives. The annotation on disk is unchanged. There is no
  annotator rename, the occurrences cache goes to version 6 (rebuilt free), and the cause
  rides the next scheduled rename (targum-internal#590).
- Russian says "known" one way and names the cantillation marks one way (David,
  2026-10-23; targum-internal#476): 91 strings. A word's stage is «знаю», marking one is
  «отметить как «знаю»», and a share or count you know reads «вы знаете» («Вы знаете
  80% слов», not «80% слов известно»); «знакомо», «знакомые» and «известно» are gone. The
  marks are «знаки кантилляции» on the parasha pages too, not «знаки распева». English is
  unchanged.
- The root lexicons' gold score accepts the conventions the two blind labellers listed
  before they saw any model answer (targum-internal#592, #596). Hebrew: a III-weak ה is
  a י, a hollow ו is a י, a I-ו is a י, a geminate may be written with two letters, a
  word-made quadriliteral accepts its source (`HE_SOURCES`), a primary noun accepts none
  or its dictionary root, patterns compare by consonants (`skeleton`), and a participle
  accepts its binyan. Russian: a fused prefix may be split, a root may carry or drop a
  listed extension, and the listed allomorphs, prefix spellings, pronoun stems and
  historical roots count (`RU_ROOTS`, `RU_FUSED`, `RU_PREFIXES`). Two models now agree on
  a root under the same rules. `--score` adds an `agreed` line: the rows both models
  settle, how many there are, and how right the shipped answer is. No spend.
- A prefix letter is never a word to learn (2026-10-30). Your Progress's "Words you
  keep meeting and don't know yet" showed a bare כ: DICTA splits a clitic off as its own
  token, a reader who tapped it had it on their list, and the list counted every token.
  That list, the practice card on Your Words and the Sentences gaps now leave out a
  one-letter form and a form met only as a closed-class word (`tables.weights.EXCLUDED`:
  של, את). The occurrences cache records those forms (version 5, rebuilt free on first
  read). The rows of Your Words still show every word on the reader's own list.
- A stretch of a recording played says whether its text was on the screen (David,
  2026-10-30; targum-internal#602). It was not while the page was hidden, the listening
  view was open or Hear first held the line back. A change to any of them while the voice
  goes splits the stretch. Kept as `event.text_on_screen` (account schema 51), unknown on
  everything recorded before. The privacy notice's clause 3.6 and the account page say
  so. Nothing on Your Progress shows it yet.
- A part finished out of sight no longer counts as words read (David, 2026-10-30;
  targum-internal#602). A playlist running on with the phone locked, or Play on in the
  listening view, finished the part and added its whole transcript to "words read" as
  well as its minutes to "listened". Finished with the page hidden or the listening view
  open, a section now adds no words. And putting a film's picture up or away while it
  plays splits the stretch, so the time before is "watched" and the time after
  "listened", where the whole stretch used to go by how the picture stood at the pause.
- Your Progress, "How you got here", is board 3 "Effort" (David, 2026-10-30;
  targum-internal#603). Two figures: words read, and time listening with watching counted
  in it and "Including 4 h 1 min of video" under it (one Watched figure where a language
  has no recordings). Each has a line against the period before ("▲ 12% vs. last 30
  days", a fall ▼ in soft ink), with none on All time or with nothing to compare. Week |
  Month | All time is a `.seg` at the head's end, in place of the pills. "Days active · N
  of 30" is a square a day, any day read, listened or watched, with no grid on All time.
  "Words this month" has three bars: new words met, saved, now known. Two records start
  today for those bars and are not filled from before: `word.known_at`, set by the account
  when a word becomes known and cleared when it leaves known, and `met`, the first
  finished section each word was met in, written when the section is measured on the push
  (schema 50). The note about what counts as read and the week-by-week chart are gone.
- Your Progress, "What next", leads with your biggest grammar gap, board 4B (David,
  2026-10-30; targum-internal#604). "Your biggest gap: הִתְפַּעֵל verbs", then "You know
  31% of the hitpa'el forms you meet, against 80% for the other common patterns", what
  the pattern does, and two of its words you met. Under it a Grammar grid, the seven
  binyanim by Past, Present, Future, Imperative and Infinitive: each square the exact
  share of the verb tokens you met in finished sections whose word you know, shaded in
  proportion, "—" under 10 tokens, the weakest row outlined, and a square opening its
  words. A pattern needs 30 tokens to be named the gap; with none, the two lists stand
  alone as before. A real table for a screen reader. A Topics slot is built and hidden
  until topic tagging exists. The binyan is the annotation's or, where it named none,
  the CC0 paradigm table's where every verb it finds agrees; the occurrences cache keeps
  each verb's binyan and tense (`occurrences.VERSION` 4, rebuilt for free). No annotator
  rename, no `SCHEMA_VERSION` bump.
- A Hebrew verb's root is denied where no Hebrew has it, and kept where the first list
  was wrong to deny it (ling-he's review of targum-internal#589, 2026-10-30;
  `verb_roots.VERSION` 2). Five entries come off the deny list because their roots are
  right: נצב, חוב, הגיח, שורה, המרה (נצב alone is 103 tokens). The CC0 table's
  hof'als filed as pu'als with the binyan's ה read as a radical (הושג under השג) and its
  three פ"י hif'ils filed under נ (הציע under נצע) are denied for every lemma, 29
  strings; הגר, הדק, הדר, הון and הסה stay, because they are roots. Nine lemma entries
  join: השתנה, נשתנה and משתנה under שתן, התיש and מתיש under נתש, דן under דון, עט under
  עטט, אלה (mostly a mis-lemmatised הללו) and נרגן. A four-letter root with a ו or a י,
  or ending in ה or ת, is a word handed back as its own root (קראה, גדול) and is denied;
  a real quadriliteral (פרסם, תכנן) has neither. A root on ו is kept only for ותר, ודא and
  וסת, in any form, so the present מוותר keeps it and a wayyiqtol וילך does not. On the
  laptop's 469 Hebrew texts, verb tokens with a root go from 83.3% to 83.2%: wrong roots
  become gaps.
- A Hebrew verb's root on the word card is right more often and there more often
  (targum-internal#589, David's decisions of 2026-10-30). About 75 roots measured wrong
  against Wiktionary (used to find them, never shipped) are no longer drawn: a
  three-letter lemma that is not a qal given itself as its root (הקל, הכה), an adjective
  spelled like a nif'al with its own נ stripped (נזיר), a root starting with ו. A verb the
  annotator gave no root takes one from the CC0 paradigm table where every verb the table
  finds agrees. On the laptop's 212 modern texts, verb tokens with a root go from 63.6% to
  81.6%, and 99.7% of the checkable ones agree with Wiktionary. "From the same root" and
  "N words from this root met" follow, and a vetoed root has no family. All of it is at
  page-build and table time: no annotator rename, no `SCHEMA_VERSION` bump, no model run.
  The language tables gain `roots` beside `words`, by register, fed by the same fold and
  `public_text` guard (`targum tables top --roots`).
- A Russian verb's card names only its true aspect partner (David, 2026-10-30). For the
  300 commonest verbs in the built Russian texts, targum's own reviewed list answers
  before OpenRussian: видеть is увидеть's partner and not завидеть's, and знать, стоять,
  ходить and помнить have none. A new "related:" line names the verbs beside it that are
  not partners, with what each adds, as in "запла́кать (begin) · попла́кать (for a
  while)". `scripts/eval_aspect_partners.py` scores the line on the top 100 verbs: whole
  lines right went from 0.660 to 1.000 of verb tokens, and partner precision from 0.735
  to 1.000, against the list itself. The list and the Russian strings are ling-ru's
  drafts and wait for David's read. design.md §12.
- Your Progress's level card has a visible heading, "Reading level" (David, 2026-10-30;
  targum-internal#574). It is the card's own h2, set as "Texts by level" and "Words you
  knew" are beside it, and the visually hidden "Your level" h2 is gone, so the part still
  has one heading. The Russian, «Уровень чтения», is ling-ru's draft and waits for
  David's read. design.md §12 also records the next card, #575: "How much Hebrew you
  understand", measured on a fixed yardstick.
- `test_the_bar_takes_the_keyboard_and_turns_no_page` no longer fails about one run in
  five (targum-internal#573). The bar always kept its keys. The page it saw turn was
  the voice's: `End` plays the recording out, and the voice turns to the last line's
  page on its way out whenever its tick lands before `Home`. The test now asks the
  page's own keyboard whether any key reached it (`End`, `Home` and both arrows), and
  accepts the first page or the one the voice left it on. 20 runs pass out of 20 (master
  failed 4 of 20). With the bar's `stopPropagation` taken out, it fails at once.
- `/readers` sends only what a page draws (targum-internal#556). Every caller got the
  whole shared shelf of ~455 texts, each measured against the reader's words: about
  430 kB of a 460 kB answer, and most of its time on the server. Home now asks for the
  shared texts the reader has had open and no catalogue, and a reader's contents page
  asks for its own row only. The Library and the arrival still get the whole answer, with
  the same fields as before.
- Home and its Subscriptions tab stop waiting on the account before the shelf
  (targum-internal#555). Home asked for `/readers` only after `/account/me` and the
  push of anything owed had answered, so a reader back from a text, who always owes a
  place, waited one or two round trips more on a phone. Now only words owed hold the shelf
  back, because they are the one thing its figures are measured against. The shelf, the
  builds, the places and the new items are asked from the page's head. Subscriptions is
  shown on its own answer wherever the arrival cannot apply. The pages look the same.
- A video whose transcript came from its subtitle file no longer bounces, and no longer
  lights the wrong word (David, 2026-10-29, on the Touring Israel interview). A subtitle
  cue runs across sentences, so neighbouring lines' spans overlap (39 of 48 in that
  video's first part). Inside an overlap, `timeupdate` lit the first line holding the
  clock and the line under the picture lit the last line begun. The lit line swapped
  twice per tick and the transcript was scrolled to each in turn: 108 scrolls and 46
  reversals in 30 s, measured on a copy of the reader. Every one of those choices now
  asks `lineAt`. Where a cue holds the end of one line and the start of the next, it
  is split between them by their letters. A cue's clock, shared by its words, lit the
  cue's first word for the whole cue. Now only a word with a clock of its own is lit
  (design.md §12: "where the recording was aligned word by word"), and the step
  buttons say five seconds on such a text. Following word by word there needs the
  subtitles aligned to the recording.
- The scene check reads «אִתָּהּ» ("with her") as «אִתָּהּ» again, not as «אַתָּה» ("you",
  to a man). `checks.addressed_gender` now decides by the vowel under the alef: a qamats
  or patah is the pronoun, a hiriq the preposition, and an unpointed אתה says nothing.
  qa found it on scene 221 once the normaliser had turned אִיתָּהּ into אִתָּהּ. All 151
  אַתָּה in the 267 scenes still read as addressed to a man.
- A short conversation is no longer listed at C1 (2026-10-29). "The key" (14 words) and
  "Renting a bike" (38) were measured Native because one uncommon word is a big share of
  a few, and the text ruler then put them on C1; before it they were "B2 and up". A
  conversation targum wrote now keeps the level it was written at (`levelmap.AUTHORED`):
  on the scenes path and the Russian scenes rungs 1 to 3 are A1 and rungs 4 to 6 A2, read
  off the scene's dialogue file, and the Conversations are B1. Under 100 words
  the measure never places a text Native, and such a text is unmeasured
  (`levelmap.NATIVE_MIN_WORDS`; the shortest Native text that is not a scene is 143
  words). `text_level`, `cefr_rows` and the stage floors share one rule, `level_for`.
  On the laptop's catalogue Hebrew goes from 112 / 96 / 81 / 45 texts at A1 / A2 / B1 /
  B2 to 175 / 70 / 66 / 40, and Russian from 93 / 100 / 124 / 100 to 130 / 63 / 124 / 99
  (every Russian scene is rung 1 or 2). `evals/shelf.json` is not re-measured here.
- Scene audio sounds less like a list being read (David, 2026-10-29; targum-internal#566).
  `scripts/voice_scenes.py` now has a cheap model (Haiku) read each scene once and give
  every turn a few words of direction, such as "calm, matter-of-fact", which go into
  that turn's speech prompt. Its brief says ordinary conversation is the default and
  nothing is excited unless the words call for it. The directions are cached by the
  scene's words and their English, so a re-run spends nothing. A scene the director
  could not answer twice is kept as neutral, so its turns are not bought again. The
  fixed 0.45 s between turns is gone. A reply now waits 0.6 to 0.9 s, an answer to a
  question 0.25 s longer, and a line that carries on or cuts in 0.3 s. The gaps carry
  room tone at about -60 dBFS instead of digital silence. Each turn is brought to -18
  LUFS (EBU R128) with a -2 dB peak limiter before it is joined. On he-06 the turns went
  from a 4.9 LU spread with a +1.0 dBTP peak to 0.3 LU and -1.9 dBTP. Spans stay exact,
  and each mp3 gets a `<id>.seams.json` beside it with those spans and the mp3's hash,
  so the shelf writer uses the known seams instead of guessing from silences, which
  short gaps make unreliable. Every bought turn is written to disk as soon as it
  arrives, so a crash loses nothing and a re-run asks only for what is missing. No
  prompt over 180 characters is sent. The direction is shortened or dropped first, then
  the pronunciation hint is said more tersely, and a prompt that still does not fit is
  refused. Prompts on he-06 as voiced ran median 96 and max 133 characters. With the
  longest direction allowed, the corpus would be median 115 and max 180.
- Your Progress's Level section, three follow-ups from qa (targum-internal#554). At a
  desk the ladder's state and count line up row to row in every language: each row was
  its own flex line, so in Russian a longer count pushed «Вам легко» and «Следующий шаг»
  along, and on the Aramaic ladder a row with nothing to read slid its state right. The
  rows are now subgrids of one grid. The bar toward the next rung is hidden from screen
  readers: as a progressbar it was read as a percentage, and named by the Next line it
  read that line twice. The Next line beside it is heard once, and nothing says a
  figure. The Connect page's example asks for "a short conversation" / «короткий
  разговор», not a dialogue. See all's Level menu (Read it now / A stretch / Hard for now) is gone (David,
  2026-10-29): beside the text level's chip, "level" meant two things in one row. A list
  opened under a band, from a shelf's See all or a Your Progress row that counts what you
  can read, says its band as a chip that clears it, and `#see/<band>` and
  `#see/now/level/<level>` still open as they did. The menu's two strings are deleted.
- How much of a text you know is an exact percentage, not a count in ten (David,
  2026-10-29; targum-internal#560; design.md §12). The chat's press card, the text card
  beside `find_text`, the add page's found rows, home's suggestion and the chat itself
  said "You know about 7 words in 10 here". They now say "You know 72% of the words
  here." / «Вы знаете здесь 72% слов.», with no "about". A share under all of it never
  shows as 100% and one above none never shows as 0%. The Tanakh map's sum says "90% of
  the words or more" in place of "nine words in ten". `level.words_in_ten` is
  `level.known_line` now. Your Progress's monthly line went exact with targum-internal#561.
- The signed-out Library loads its files once too (targum-internal#558). `/library` and its
  kind pages were left off #549's list and still carried 65 kB of faces and 119 kB of CSS
  inline on every visit. They now work like the other public pages: whole on a first visit,
  named by address once kept, warming the same public set. Measured locally on the phone
  profile: a first visit's LCP from 1.02 s to 0.76 s (Russian 1.14 to 0.72), a second
  visit from 0.96 s and 83 kB to 0.64 s and 21 kB. Screenshots are identical at 390 and
  1440 in both languages once the faces are on.
- The signed-in Library draws its rows before `/readers` answers, and asks for its
  catalogues in one wave (targum-internal#557). It waited for the shelf's files and the
  account's answer together, so a returning reader whose files came from the cache still
  waited about a second on a phone. The catalogue's order and the build file also came in
  a second wave after the first draw. Now the head asks for all five files at once. The
  rows are drawn as soon as the shelf is in, from a slim copy of the last answer this
  browser kept (`targum:library-last`, which sign-out sweeps), or from nothing on a first
  visit. What is built, how much of each text is known and the shelves that follow from
  it are drawn again when the answer comes. While the shelf is on its way the wait holds
  a screen's height, so arriving rows no longer push the footer down. Measured on the
  phone profile against a local serve with a 203-reader shared shelf: warm LCP went from
  1.47 s to 0.77 s and layout shift from 0.41 to 0.00. Cold LCP stayed about the same
  (2.83 s to 3.00 s; the first visit's bytes still decide it), and its layout shift went
  from 0.41 to 0.003. Live before the change, as the test account: 4.05 s cold, 1.69 s
  warm, shift 0.41. Once the answer is in, the page is the same as before.
- A reader opened on targum.page loads its files once (targum-internal#559; design.md
  §12, approved by David 2026-10-29). The server hands a browser opening a reader the
  page with today's stylesheets, scripts and faces named under `/assets/` and its
  recordings under `/clips/`, so they are kept; the reader on disk, a save for offline
  and a download stay whole and fetch nothing, and the worker never keeps a page that
  needs its files as the copy for the plane. Measured locally on the phone profile with
  the files kept: Ruth 1.34 s / 159 kB to 0.69 s / 14 kB, a scene 0.85 s / 325 kB to
  0.66 s / 14 kB.
- The pages in front of the account load their files once (targum-internal#549; design.md
  §12, approved by David 2026-10-28). The front door, a text's public page, About and the
  legal pages carried 65 to 122 kB of faces and up to 290 kB of CSS on every page under
  `no-store`. They now work like desk pages: whole on a first visit, and named by
  address once kept. A stranger's first page warms only what the public pages use, in
  its language: 188 kB in English and 272 kB in Russian, never the desk's ~0.9 MB of
  scripts, catalogues and other faces. The kept-files cookie keeps its name and holds
  that smaller set's hash. Measured locally on the phone profile, a first visit's LCP
  went from 1.13–1.28 s to 0.78–0.91 s, and a second page from 95–112 kB to 6–10 kB.
  Screenshots match pixel for pixel at 390 and 1440 once the faces are on.
- Subscriptions answer a thumb (targum-internal#475 re-audit). Measured on a phone, the
  Subscriptions tab's Pause and the way into a subscription were 32px wide side by side,
  "‹ Subscriptions" was 21px tall and the only way back from one, and the names and
  titles that open a subscription or a text were their line's height. The two presses
  take 44px, and the links a centred 44px reach that crosses no other press. All six are
  in `test_brand`'s thumb registry, and a browser test taps around each one.
- The front door's last polish from design's §14 pass (targum-internal#477). The word
  card's Here row puts its meaning on a line of its own under the form, so "crack" /
  «разбивают» no longer wraps alone at 1440 (polish 4). Under a coarse pointer the bar's
  mark and the why-fold reach 44px, and the chat demo's "Save as a text" and a text
  page's way back to the Library answer a tap through a centred 44px reach while the
  words keep their size (polish 8). No copy changed.
- deploy/INCIDENT.md has a drill for each of the five kinds of trouble on
  targum-internal#482 (a rollback, last night's database, a provider down, out of
  credit, the box unreachable), with the date each last ran. `targum drill-credit` sends
  the out-of-credit mail once as a drill, through the code a failing build uses, without
  spending and without touching the live four-hour limit. The runbooks say plainly there
  is no outside monitor yet (David, 2026-10-28: "Not before Launch"); they used to say
  one heard a dead box. A copy that did not leave the box now says rclone's error, not
  its config notice: every failed night since 2026-10-26 said only "failed to get", where
  Backblaze was refusing with 403 storage_cap_exceeded, and INCIDENT.md says what to do
  about a full bucket. `tests/test_runbooks.py` checks that every unit and `targum` command the
  runbooks name exists.
- A /sync on /library no longer comes back 502 now and then (targum-internal#495).
  The Library asks for a couple of hundred thumbnails within a second, Caddy opens a
  connection to us for each, and the server listened with `socketserver`'s backlog of
  five: a connection that arrived while the queue was full lost its handshake and was
  reset about a second later, under whichever request rode on it. The box counted
  169,443 such overflows since boot; two resets reached a reader as a fault, both a
  /sync during a burst of 121 and 206 thumbnails. The queue is 1,024 now (the kernel
  caps it at `somaxconn`, 4,096 on the box). The other /sync 502s in the log answer in a
  millisecond and fall inside a service restart; `sync.js` sends the same changes again
  after either.
- In a reader, the talk drawer's box no longer cuts its line mid-letter
  (targum-internal#472). A textarea's placeholder takes no ellipsis in Chromium, and the
  drawer's field is about 235px at a desk and 158px on a phone, so "Ask about the text,
  or write in Hebrew" read "or wri". The line is David's shorter one now, "Ask about it
  or write in {language}" («Вопрос о тексте {language:adv}»), and where even that does
  not fit, which is every phone, "Ask about it" («Спросите…»), chosen by measuring the
  field. The box keeps the reader's line when the conversation switches language. The
  Reading line's sentence now carries its `lang` and `dir`. design.md §12 says so.
- Home's one card stays for a reader with a long record (qa on targum#958). Home sent
  every finished text's id in `/suggest`'s address, and about 2,000 of them passed the
  server's 64 KB request line, so the card was never drawn. They go in a POST body now;
  a GET with `?skip=` still answers.
- A new Hebrew reader starts on scene 1 of the A1 path again (2026-10-27, a regression
  since aec01564). The 27 B1 conversations are `scene-he-01…` and number from 1 too, and
  every page read the number alone: since `/readers` lists shared texts newest-built
  first, B1's scene 1 became Start here in the Library and the arrival, the Scenes list
  went 1, B1 1, 2, B1 2, and the reader offered A1's scene 2 after B1's scene 1. The code
  after `scene-` now names a series (`""` for A1, `he` for B1, `ru` for Russian):
  scenes sort by series then number, Hebrew's path and Start here are A1's alone, the
  next scene stays inside its series, and the shelf shows one card per series. Ids are
  unchanged.
- A gap in a scene series no longer ends it (2026-10-27). B1 has no scene 15, 25 or 29
  and Russian skips 4, 5, 16, 19, 48 and 64, and the reader looked only for number + 1,
  so after scene-he-14 there was no next scene. It now offers the next higher number in
  the same series. The English-title draft also drops the series code from a prefixed
  scene's slug (`scene-he-07-the-lease` is "The lease").
- Your Progress no longer says Aramaic texts aren't placed by difficulty (2026-10-25).
  Since targum#936 Aramaic has a ladder, so part 3 now says it lists Aramaic texts at
  your level once the library's Aramaic is measured. Once the 41 Aramaic rows are
  measured, the texts at your level are listed as in any other language. The Russian line
  is a draft for ling-ru.
- The note under "Learned on targum" is one sentence now: it says what the count holds and stops (David, 2026-10-25).
- Your Words keeps its table inside its card at every width (David, 2026-10-24: "design
  seems to be broken"). Since targum#919 kept the AI Assistant's room on both edges of
  the column, the column is 1198px at 1440 in English, and the page still asked the
  window whether the practice card fitted beside the table: the table ran 41px past its
  card at 1440, 64px at 1280 and 115px at 768, and ignore sat under Practise these. The
  card now stands beside the table only while the table's narrowest fits beside it, and
  goes above it otherwise; the list takes the phone's rows wherever it is narrower than
  its table; a stage's name may take two lines; and a Hebrew word's dictionary form
  stands under the word instead of at the cell's other edge. The same shoot, every
  signed-in desk page at 360 to 1920 in English and Russian, found one more: Your
  targums' Subscriptions tab at 768 broke «Недельный» mid-word and ran «Каждый
  понедельник» into the next column; its table takes the phone's rows wherever it is
  narrower than its columns need. `test_desk_fit_browser.py` holds both.
- The grammar/8 re-read (targum-internal#509 and #307, ling-he's spec; part (b), after
  #929's render-time index). A modern hollow, geminate or I-nun verb gets its root and
  binyan from a list ling-he reviewed: מת is פעל of מ־ו־ת, הביא is הפעיל of ב־ו־א, and
  רב, דן, צר and מל, which could be two roots, still get none. רָאִיתִי is "saw" under
  ראה, not "showed" under הראה, and eight more hif'il lookalikes go back to the qal. A
  present with no tense is filed under its past: Mishnah's אוֹמֵר is אמר's, and הולכים
  is הלך's where the model stood the word in. נָתוּן is root נ־ת־ן, not a nif'al of תון,
  and ten more passive participles keep their word and get their root. Biblical ילך
  (Strong's H3212) is הלך, headword, root and gloss, and the Tanakh band table counts the
  two as one. Stress: a verse's last word is stressed where its silluq is (לָֽחֶם is
  LAchem), geresh muqdam and ole-veyored are read, the segolate rule places an accent the
  accents cannot, a furtive patah is no syllable (לוֹקֵחַ is loKEach), -תִּי is always the
  first person, a quiescent א sits inside a segolate (וַיֹּאמֶר is vaYOmer), and לָאו is
  lav. A word pointed only here and there (Brenner's פּתח) gets no sound rather than a
  sound with no vowel. Renames `grammar/7` → `grammar/8`, `oshb/7` → `oshb/8` and
  `phonikud/3` → `phonikud/4`, which re-reads every Hebrew text: held for a weeknight
  deploy with the long box rebuild, the laptop rebuild and a parasha and daily re-cut. No
  spend.
- "Learned on targum" counts a word marked anything other than known that later became
  known (David, 2026-10-24). The count already took new, still learning and almost
  known; it now takes ignored too, and the note under it says what it counts in plain
  words, in English and in Russian (a draft for David's read). A word first marked known,
  or claimed on "Words you may already know", still does not count. Undo after an
  ignore hands back a known word without counting it. The store keeps a word's current
  stage and a flag written when it crosses to known, not a history of its stages, so
  words that crossed from ignored before this change are not counted.
- A conjugation table for the hollow, geminate and I-nun verbs Open Scriptures files under
  their root (grammar/8 part (a); targum-internal#509 and #307). בוא in hif'il now draws
  הֵבִיא, נגש draws הִגִּישׁ and תמם draws תַּם: the table indexes each such verb under the
  roots its pointed lemma allows, and a qal's hollow letter is the one its own forms spell,
  so Job's שׁוּר "behold" never gets שָׁר "sang". Strong's שום is looked up as שים. Render
  time only, with no annotator rename: measured over the library's 114,291 verb tokens,
  coverage goes from 83.8% to 86.5% and "no candidate" from 14,768 to 11,694, with nothing
  new refused. The card's stored root waits for the grammar/8 re-read.
- The connector hands a Torah portion's lines to a host (targum-internal#527).
  `open_library_text` read a portion's sentences from `read/<folder>/`, but a portion's
  build is in `read/<folder>/print/`, beside its readers, as `ship-parasha.sh` leaves it.
  So parasha-bereshit came back with no `lines` and no `how_to_read`, and Claude fetched
  the page instead. It now reads them from `print/`. The connector eval has a portion
  scenario. Daily cycles are not library rows and never came through this tool.
- A Tanakh word's card says what it means in a word or two, from STEP Bible's brief
  lexicon, where it read Strong's King James thickets, typos included ("by
  extenssion"; targum-internal#510, David 2026-10-24, licence and spec by ling-he).
  בָּרָא is "to create", רוּחַ "spirit", עֶבֶד "servant; slave". Only the Gloss column of
  TBESH is read (Tyndale House, CC BY 4.0); its Meaning column is Online Bible's and is
  never read, stored or shipped, and a test fails if any reaches the table. The file is
  fetched at a pinned commit by `targum models fetch scripture`, which `deploy.sh` now
  runs before the rebuild, and never vendored. One gloss per Strong's number, the letter
  the Tanakh uses most, so every עָשָׂה is "to make" and none "to press". A name never
  stands for the word: דֶּרֶךְ is "way", not "Way", סוּס "horse", not "Horse (Gate)",
  and צָבָא "army", not "Hosts". A deploy that cannot reach STEP Bible warns and goes on.
  `annotate/tbesh_changes.tsv` is both the change note the licence asks for and the hand
  fixes (רע "bad", כֵּן "so", פֶּה "mouth", טוֹב "good"). Where TBESH has nothing, Strong's stays. Reader pages whose
  meanings show one, and the How page, say "Meanings from STEP Bible · CC BY 4.0 ·
  shortened by targum", linked. No annotator rename and no spend; parasha and daily need
  a re-cut after the deploy.
- The signed-out Library stands by language and kind (targum-internal#519). It was one
  list of 1,315 texts in five languages under a line about Hebrew, about 237,000px tall
  at 1440, with the waitlist under all of it. Now Hebrew comes first, then each other
  language by its size, each headed with its count, and inside each the signed-in
  Library's kinds, six texts apiece with "All N →" to a page of that kind
  (`/library/k/<language>/<kind>`, noindex for now). Under the lede, "Free to read once
  you're in." and Join the waitlist. It wears the front door's bar, ground, cards and
  face (David, 2026-10-24) and carries no script and no reader stylesheet: 806 kB became
  201 kB (84 kB gzipped) in English. The text and legal pages speak in the chrome's face
  too, not the platform's (#477, polish 5), and a Hebrew word inside a Latin byline says
  it is Hebrew (#477, polish 10). A noindex no longer rides on to the next page of a
  kept-alive connection. A language the visitor pressed (`?lang=ru`) goes on every link
  the page draws, and a kind of videos counts videos.
- The public bar keeps Sign in on a phone (targum-internal#528). Under 30rem it used to
  drop it, so a reader coming back with an account had no way in from the top of the
  landing, the olim's page, the signed-out Library or a kind page: the foot's Sign in
  was 8,100px down on the landing and about 26,000px on the Library. It stays now, on
  the bar's one line beside Join the waitlist at 320 and 390 in English and Russian,
  44px across and up under touch, carrying a pressed `?lang=`. To make room the phone
  bar tightens its gaps and shows only the language you can press; under 23.25rem the
  language waits in the foot, as it did under 22.5rem.
- A word on the longest aliyah answers its first tap about a quarter of a second sooner
  on a phone (targum-internal#503). Phone profile with recordings, across builder's and
  qa's runs: Ki Tavo's sixth 1.77 s → 1.44–1.53 s, Bereshit's first 1.39 s →
  1.19–1.22 s. What a tap does not need left `reader.js` for `reader-rest.js`, after the
  faces: the lenses and the case lens, export and the Anki deck, shnayim mikra, the
  bar's panels and the keys card, full screen, the keyboard and keeping a phrase (70.5 →
  57.6 kB gzipped). The closures for where to go next and the unpaid chapter joined
  `reader-after.js`. The conjugation tables and a text's lemma renames ride in the block
  after `reader.js`; the card draws its fold from the first tap and fills it when they
  come. The page is laid out once while it is set up, not three times. The rest joins
  about half a second after the first tap could be answered, and a press of the bar
  before then does nothing, and a shnayim mikra walk in progress is laid out as it
  arrives. The parasha and daily pages need a re-cut to carry it. design.md §12, "What a
  first tap does not need waits after the faces".
- The connector's results say what the model must follow beside the links they carry
  (targum-internal#527). Live on 2026-10-23 Claude put links mid-sentence and read
  Genesis from memory, and ChatGPT wrote "Targum", hid links behind titles and gave a
  /build link with no cost. Every tool result over `/mcp` now ends with a short note in
  a second block: write targum in lowercase, and where there are links, each on a line
  of its own and the links last; a link the reader confirms on (a build, set,
  subscription or reading aloud) goes with its credits, 0 included. `open_library_text`
  hands over a text's lines, eight at a time from `from_line`, where it opens now, and
  read-with-me asks the host to open the text on targum and read from it, never from
  memory. The connector eval checks all four. Nothing costs more and nothing spends
  sooner.
- design.md §12 records the connector handing a host a text's lines (David, 2026-10-23;
  targum-internal#527): eight at a time, so a host reads targum's text and not its
  memory; a reader's own copy only where they shared their record, the shared shelf and
  the portions kept for everybody for anyone; beside `sentences_with`; spends nothing.
- The other languages' polish left from #476 (targum-internal#523). A desk page's column
  stays centred: the room kept for the AI Assistant's pill went on the end edge only, so
  the column slid 25px off centre in English and 6px off the edge in Russian; now both
  edges keep it once the window has room. The foot tells somebody learning Italian,
  French, Russian, Yiddish or Aramaic "Learn languages from anything." instead of to
  learn Hebrew; Hebrew keeps its own line. The arrival's level step says why Continue is
  asleep ("Choose a level to continue."), tied to it with `aria-describedby`. On a phone
  the Russian word card's «пропустить» keeps its whole word instead of running past the
  sheet's edge. A text page says its place in the page's language («Писания · Рут»).
- The Library draws its first card under a second and a half on a phone
  (targum-internal#484). On qa-claude's profile (150 ms, 1.6 Mbps, 4x CPU, cold) it was
  about 2.1 s in English and 2.2 s in Russian, and its shelf was asked only once the whole
  page had arrived. `library-early.js` now asks for the shelf, `/readers`, `/jobs` and
  `/portions` from the page's head. A row's blurbs are a file per page language
  (`catalogue-he-en`, `catalogue-he-ru`), so an English page no longer takes the Russian
  ones. The catalogue's order, what a Build press sends (`catalogue-he-build`; a press
  that comes first waits for it) and the English blurbs a Russian page searches arrive
  after the first card. A desk page sent whole (a first visit) keeps its faces, about 67 kB
  gzipped, in an inert `<template>`, and `warm.js` puts them on at `load`, or on the
  Library once the shelf is drawn; until then the page wears the platform's face. Every
  desk page paints sooner with it (first paint about 0.7 s to 0.4 s), and Your targums
  goes from about 1.45 s to 1.1–1.2 s. `scripts/measure_pages.py` is the
  profile as a script: it starts a keyless hosted-style serve on a scratch copy and
  measures every main page, with no spend.
- Russian names a language in its case mid-sentence (David, 2026-10-23;
  targum-internal#524): «На иврите пока ничего нет.», not «На языке «Иврит» пока ничего
  нет.». A translation asks for a form on the same blank, `{language:in}` («на иврите»),
  `{language:adv}` («по-русски») or `{language:nom}` («иврит»), and `language-in.*`,
  `language-adv.*` and `language-nom.*` hold the forms for the eleven languages targum
  names; a language with none is quoted as before. 37 Russian sentences changed, on the
  server, the templates and the scripts alike. English is unchanged.
- A text page credits the translation it shows (targum-internal#521). In Russian it set
  Russian lines beside the Hebrew and credited the English (Metsudah, "Official English")
  under an English "Translation", and its JSON-LD said `inLanguage: en`. The credit and
  the JSON-LD now follow the lines: a published rendering when the lines are copied from
  one (a sample line's new `from` names it, with its licence linked), and otherwise the
  English the lines were translated from, with «Эти строки мы перевели с английского.»
  An English page credits only its English: Onkelos, Rashi and the Russian Torah are not
  on it. A row with a bought translation and no rendering says "We translated this
  text." A text in Russian shows its English opening on a Russian page, not a model's
  Russian of its own English original. The heading is keyed («Перевод» / «Переводы»).
- `test_a_refused_answer_is_not_kept_for_the_page` no longer fails on about a quarter of
  CI's browser jobs (targum-internal#526). The page was right: `building.js` asks
  `/account/me` as it runs and `sync.js` only at DOMContentLoaded, they share the question
  while it is out, and a refusal is forgotten once it is back. On a slow runner the 502
  came back before the rest of the page had run, so the later scripts asked again, as
  they should. The test now holds the first answer until the page has loaded.
- The Russian interface after ling-ru's read-through of the whole catalogue
  (targum-internal#476): 93 strings. A language name no longer sits capitalised
  mid-sentence («На языке «Иврит» пока ничего нет.», not «На языке Иврит…»); counts that
  broke after 1–4 or 21–24 say the number after a colon or use «ч»; «Играть» became
  «Включить»; Continue is a block («в блоке «Продолжить»»); a queued text says «В очереди
  перед ним {n} текст» as the other queue lines do; «Экспериментальный» became «Пробный»,
  which fits the badge; and plan, prompts, waitlist and the AI assistant have one word
  each. English is unchanged.
- Your Progress no longer scrolls sideways on a phone (targum-internal#522, the last
  blocker on #471). Under 40rem the time figures wrap instead of holding three 91px
  columns, so "9 ч 28 мин" no longer runs into the next figure: words read take the whole
  width and the times sit beside or under each other. On an Aramaic page in Russian the
  bar's long badge pushed the account 25px off the edge; the badge now ends in an
  ellipsis instead. "Learned on targum" is the ledger's quiet last line rather than text
  on the desk ground under it, and when the story fails to load What next's two halves
  each say so instead of standing empty. A browser test loads Progress in Russian at 390
  and 320 for Hebrew, Aramaic and Yiddish and holds the page to its width with no figure
  overlapping another.
- CI no longer installs ffmpeg from the apt mirror, which still failed several times a
  day after the timeouts and retries below (run 39907694995 on master, 02a6c102). It
  takes BtbN's static 8.1 build of `ffmpeg` and `ffprobe` from GitHub, checks it against
  the release's checksums and keeps it in the Actions cache, keyed on the version and the
  runner, so a run with the cache warm fetches nothing. apt is the fallback only, for
  when the download fails or BtbN drops the 8.1 branch.
- The signed-out Library in Russian draws its rows in Russian (targum-internal#520). Each
  row's name and blurb come from the catalogue's `named`/`blurbs`, the same fields the
  text page reads, and a book's place takes the Russian book names («Писания · Рут» for
  "Ketuvim · Ruth"). Rows with no Russian yet (162 of 1,306) show the English, marked
  `lang="en"`. Nothing new is fetched or stored; the English page is byte-for-byte as it
  was, and the Russian one grows by its Cyrillic, about 20 KB gzipped.
- The chat's last loose ends after #884 (targum-internal#472). The labels over a recast,
  "you said" and "corrected", came from the stylesheet in English. They are catalogue
  keys now (`chat.recast.*`), put on the pair as `data-said`, so Russian says them in
  Russian. The box's placeholder is shorter ("Hebrew or English", «Иврит или русский»), so
  it fits a phone's one-row field. Hear and the quote card's source link and More options
  are in `test_brand.py`'s 44px registry, which keeps their reach from drifting.
- A shared link to /about shows the picture and says what the page is (targum-internal#518).
  It was the one page in the sitemap with no public head: no description, no `og:` tags,
  no `twitter:card`. It now includes `_public_head.html.j2` like the others, keeps its one
  address for every language, and a test holds the tags in English and Russian.
- Sign in reads again on the four legal pages (targum-internal#516). The documents' link
  rule in `public.css` was more specific than the corner's call to action and painted it
  ink on its own ink fill, about 1.1:1; it now reaches the document's links only, and a
  browser test holds the button to paper on ink at weight 600 on all four pages.
- Every Hebrew run on the front door and /aliyah says it is Hebrew (targum-internal#517).
  None of the 68 carried `lang`, so a screen reader read them in the page's English or
  Russian voice. The templates, the shared band and what `landing.js` draws (the word
  card, the film's lines and caption, the Genesis verses, with Onkelos as `arc`) now
  carry `lang` and `dir`. A brand test reads the rendered pages for Hebrew with no
  language around it, and a browser test presses every word and walks the Torah demo.
- A host that trickles bytes can no longer hold a build (targum-internal#511). The fetch
  door's 30-second timeout is, on a streamed response, a floor of one byte a second rather
  than a cap: a host sending a byte every half second held a 2-second read for fifty
  seconds. Every fetch through `ingest.url` (pages, openings and downloads, direct or
  through the proxy) now has a deadline from first knock to last byte, redirects
  included: 90 seconds for a page or an opening, 30 minutes for a download. Past it the
  door says it couldn't open the page, as it does for a timeout, and a half-written
  download is removed.
- Subscriptions' last three loose ends after #883 and #890 (targum-internal#475). An
  unsubscribed subscription with nothing listed says "You're unsubscribed, so nothing new
  comes here." instead of promising new ones. A Resume the door refuses with 409 (a
  channel or podcast unsubscribed meanwhile in another tab) goes to the confirm page the
  door names, on the subscription's page and on the tab's row, instead of "We couldn't do
  that". And the Library's News says Subscribed on a topic you follow already, going to
  its own page rather than the confirm page again.
- Database copies on the box are `0600 targum` rather than `0644` (targum-internal#514).
  The copy `deploy.sh` takes before an install runs under `UMask=0077`, and so does the
  nightly `targum-backup.service`; the two copies `deploy/ROLLBACK.md` has you take by hand
  are chmodded straight after. Every restore step reads a copy as root, so nothing that
  reads them changes. Copies already on the box keep their old mode until chmodded once.
- "Met in" from a Torah book opens the portion at the verse, with the word marked
  (targum-internal#506). A Torah book is read as its portions, and its own page forwarded
  by chapter alone, so the link landed on the chapter's first verse with nothing marked.
  The link now names the verse (`/torah/Genesis.12.5?met=…`), read off the book's
  `segments.json`, and the reader marks the word in the row that answers to `#12:5` as
  well as in the row named by its sentence. Without the portions built, the book opens as
  any text does.
- Root no longer writes inside targum's uv tools (targum-internal#513). `deploy.sh` and
  `rollback.sh` gave the targum tool back with a root `chown -R` before each install; it is
  now a repair of only what is not targum's, by `find . ! -user targum -execdir chown -h`
  from inside the tool, so it never follows a symlink the service could have put there.
  The tool is entered with `cd -P` and its real path checked first, and the deploy or
  rollback stops if a symlinked directory above it leads anywhere else; INCIDENT.md's hand
  repair does the same. The install runs from `/` rather than root's closed home. The install itself, and
  `provision.sh`'s yt-dlp install, run under `runuser -u targum --`, and provision's plugin
  check runs the tool's python as targum, where it used to run it as root and leave a
  root-owned `__pycache__` that stops the nightly upgrade, as it did for 18 hours on
  2026-10-22. Pinned by `tests/test_deploy_backup.py`. Reaches the box with the next deploy
  or rollback; provision.sh only on its next run.
- The ship scripts no longer write as root inside the service's own folders
  (targum-internal#515). `ship-parasha`, `ship-daily`, `ship-weekly`, `ship-shared` and
  `ship-audio` receive with `--rsync-path="runuser -u targum -- rsync"`, run their remote
  `mkdir`, `mv`, `rm` and `install -d` as targum, and drop the root `chown -R` after, as
  `deploy.sh` does for the covers since targum#889: a symlink the service planted, or a
  symlinked parent, can no longer lead a root write or chown out of `/var/lib/targum`.
  The index files and the weekly's folders go by rsync rather than scp, which cannot run
  its far end as anyone else. Writing `/etc/targum/targum.env`, the catalogue and the
  restart stay root. The output and the checks are unchanged. Pinned by
  `tests/test_ship_as_targum.py`.
- A failed nightly yt-dlp upgrade mails `TARGUM_ALERT_TO` (targum-internal#513). The
  cron's `MAILTO=root` reached nobody, and on 2026-10-22 an upgrade that stopped halfway
  left YouTube, Instagram, TikTok and Facebook imports off for about 18 hours. The line
  in `/etc/cron.d/targum-ytdlp` now runs `targum ytdlp-stopped` when the install fails.
- `deploy/ROLLBACK.md` and `deploy/INCIDENT.md` after their first drill (2026-10-22,
  targum-internal#482): both say when they were first run; `rollback.sh` is the first way
  back for a kept build and needs `--keep-catalogue` or `--catalogue` with no terminal;
  and INCIDENT.md says what a `warn yt-dlp` in preflight means, where the nightly
  upgrade's log is, and how to give root-owned files back to `targum` and rerun it.
- CI's ffmpeg install gives up on a slow mirror in eighteen minutes rather than eighty. It
  held the job for 30-80 minutes four times on 2026-10-22. The mirror crawls rather than
  stalls, so the first cut (four minutes, one retry) only killed downloads in progress:
  the install now skips ffmpeg's recommends (227 MB nothing uses) and has three attempts
  of five minutes, each resuming what the last one fetched. Within an attempt apt drops a
  connection silent for thirty seconds and retries it, up to three times.
- The chat pill's finish (targum-internal#472): design's eleven blockers, five of its six
  polish items and ling-en's fourteen lines. A door to a text reads on its fill (it was the
  accent's brown on teal, about 1:1) and says "Open {title}" in the title's own language,
  from titles the server now sends beside each answer (`doors`), never the folder; with no
  title it says "Open the text". Pressed open, the drawer is modal: `aria-modal`, and the
  page behind the scrim is `inert`, so Tab stays inside. Signed out, the drawer says "Sign
  in to talk to targum." with Sign in, where it was a blank sheet. With no connection the
  band is one row at the top of the frame. A corrected recast has a visible "Why?" press.
  A turn says "We're writing an answer…" from the moment it is sent. The box's placeholder
  stays on one line. Hear and the quote card's two links reach 44px under a thumb.
  Continue's title carries its language. Offline, the pill is greyed by its colours, so its
  reason keeps full ink, and is said once. Try again stands on its sentence's line; a
  conversation opens at its newest turn; the chips step aside while Chats is open; the
  reset date never breaks. The drawer opens the conversation you were in when it was seen
  in the last hour (David, 2026-10-22; design.md §13). Copy: Chats; errors say what to do
  next; Select, and the list is under Words in Your targums; "You've reached today's chat
  limit"; "audio and chat"; "of audio or video"; "Waiting behind {n} other texts".
- Subscriptions and news topics at the finish bar (targum-internal#475): design's B2–B7,
  B9–B11, polish 1–5 and ling-en's eighteen lines (B8 and B1 are targum#883). While the
  list is on its way the tab and a subscription's page say so, and past 3 s that it is
  slow, with Try again. The Library's News lists the eight topics as rows, each with
  Subscribe going to the confirm page, and an empty News chip says "You don't follow a
  news topic yet." with the way there (David, 2026-10-22). A topic is named by the
  catalogue in the page's language ("Sport", not "sport"); a channel's or an outlet's name
  is marked Hebrew only when it is written in Hebrew letters; a Hebrew name or title inside
  a sentence is a run of its own. A cap smaller than one new one says "less than one new
  one" in clay and never rounds up to one. The tab is a list, not a one-row table; the
  confirm page's mosaic fills its tile; the chips' counts are full ink. No connection is
  said once, by the band; a free reader meets "Payments open soon" and See plans with no
  greyed presses; an article with no picture takes no tile on a phone; what a press did
  is said under the head; a source that didn't answer offers Try again. The waiting rows
  are rows with a hairline between, not cards, since the tab's card holds them.
- A scene voicing request has a wall-clock deadline (`scripts/voice_scenes.py`). urllib's
  `timeout=` bounds each socket read on its own, so an answer that trickles never trips
  it. Each request now runs in a worker thread that is
  given 90 s in all (`--deadline`); past it the socket is shut, the request is reported
  to `say`'s `on_cutoff` as possibly billed, and the turn is retried after 10 s and 20 s,
  failing with a `CutOff` (a `TimeoutError`) on the third. Tested against a fake model
  on 127.0.0.1 that trickles a byte every 50 ms. The Hebrew B1 re-voicing that stalled
  on 2026-10-26 was not this: `pmset -g log` shows the laptop, on battery, going to
  sleep a minute into the run, and nothing in a sleeping process can time out.
- A speech answer with no audio in it no longer kills the shelf run (targum-internal#566).
  The whole-shelf re-voice died on 2026-10-29 at turn 9 of 218-after-the-accident with
  `KeyError: 'parts'`: Vertex sent a candidate with no content parts. `say` now reads
  the answer's `finishReason`, flagged `safetyRatings` and `promptFeedback`, raises
  `Refused` with them, and asks once more first, since an empty generation can be
  transient. In `voice_shelf.py` a refused turn marks its scene `failed` with that
  reason and the run goes on to the next scene; every such answer, audio taken out, is
  appended to `refusals.jsonl` beside `progress.json` with its scene, turn and line.

### Added
- `/credits` credits the word counts (David, 2026-11-01; targum-internal#580, #581). A
  "Word counts" section under the voices says the yardsticks measure how much of everyday
  conversation, classic literature or the Bible a reader understands, and that only
  counts are kept, never text. It credits OPUS OpenSubtitles with Lison and Tiedemann's
  2016 citation and a link to opensubtitles.org, "Project Ben-Yehuda volunteers" with
  benyehuda.org, and the Open Scriptures Hebrew Bible Project (CC BY 4.0) over the
  Westminster Leningrad Codex (public domain). The Russian strings are drafts. `/about`'s
  rule is unchanged.
- A word is said by a person where one recorded it (David, 2026-10-31;
  targum-internal#610). `scripts/fetch_lingualibre.py` reads Lingua Libre's Hebrew
  recordings off the Commons API, one request a second, with each file's licence and
  speaker read off its own page. CC0 and CC BY-SA pass, and anything else is counted and
  left: 3,512 kept, 44 CC BY and 59 non-Hebrew skipped. It writes a private manifest
  beside the files in the cache (`voices.folder()`, `/var/lib/targum/cache/voices/` on
  the box), and `--download` copies Commons' MP3 of each. `/say-word` answers with the
  person's file where the word matches: the exact pointed form first, then the bare form
  where only one recorded word has those letters. It is free and makes no claim, and the
  voice says everything else as before. The reader's card says "Said by YaronSh · CC0"
  under Hear, linked to the new `/credits`, which is open to strangers and lists every
  speaker, licence and file. On Your Words the button's title says it. Coverage: 33% of
  the tables' top 5,000 lemmas, 66% of the top 1,000 and 94% of the top 100.
- What to read next is chosen on running words, by one chooser (David, 2026-10-31;
  targum-internal#612, epic #617). `coverage.Index.running` reads the per-text counts the
  lemma index has carried since #95: each word weighs as often as it comes round, with
  names, numbers, one-letter clitics and ignored words left out. `choose.key` is the one
  sort Home's card (`suggest_next`) and Your Progress's "Texts at your level now"
  (`touchstones.at_level`) both use. A text fits from 90% of its running words, the
  nearest to 94–97% comes first, a real text comes before a scene, and a text at 99.5%
  never comes before one in the band. Home used to offer the most-known text first. A
  Hebrew beginner's card is a real text when one fits, and their next scene otherwise.
  "Something else" beside Open it offers the next best text, of another kind or
  collection where one ranks as well, and asks no reason. Candidates come from a list of
  sources (`CANDIDATE_SOURCES`, the shelf for now) and each row says its `origin`, ready
  for the fresh finds of #619. Each suggestion logs its
  running and distinct shares side by side. Recording the suggestions themselves waits on
  notice wording. Russian: «Что-нибудь другое» (draft).
- Read next offers things to read targum found in the news (David, 2026-10-31;
  targum-internal#619, epic #617, plan `docs/web-discovery-2026-10-31.md`). An hourly
  round on the box reads the items the followed feeds already hold for `search_sources`,
  takes each new article's words from the feed's full text or one fetch through the door
  (robots.txt honoured, closed hosts skipped), screens the host and the words, scores the
  words and lets them go. The pool (`find`, `find_lemma`, `find_run` in `targum.db`,
  schema 52) keeps a link, its metadata and a bag of lemma counts for a week, never the
  text, and names no reader. The scorer is a form → lemma map built from the public
  shelf's DICTA annotations through `tables.public_text` (`targum finds forms`, built and
  checked on the box by `deploy.sh`), with prefix stripping, the haser rule, and a suffix
  fallback onto lemmas the map holds. `targum finds calibrate` reruns plan §2.3 on the
  shelf by series folds: on the laptop's 60 modern texts the mean error is 1.4–1.6 points
  for readers of 2,000–6,500 lemmas with no bias, and a frozen sample in the suite holds
  it under 2.5. Home's card offers a find in the band (never within 1.5 points of the
  floor, never one more than 8% unplaced, never one costing more credits than are left),
  ranked by the same `choose.key` beside the shelf, with no network call on the request.
  Open prices the link as Add does and presses it through `Library.press` as the
  reader's own import; a higher quote goes to Add's confirm and builds nothing. Finding
  is targum's spend against `TARGUM_FINDS_BUDGET_USD` ($30 a month), never a reader's.
  The back office counts the pool by language, rung and topic, drops by reason, the last
  calibration and the month's spend. Hebrew only: Russian measured 4–8.5 points off and
  waits for a map of its own. Russian strings are drafts.
- The language tables, slice 1 (targum-internal#577): `src/targum/tables/`, kept in the
  corpus ledger (`TARGUM_LEDGER`) under `meta.tables_schema` and never exported or
  served. `contribution` and `tally` rows are append-only, with source, licence, tool and
  origin on each. A text folded again under a new annotator name supersedes its old
  count, so totals never double. `tables.fold` counts DICTA lemmas, with the part of
  speech as the variant, and the 2- and 3-lemma runs inside a segment. A run made only
  of function words is skipped, and a name is counted as `<NAME>`. The register comes
  from the catalogue entry. Our own scenes count under `scenes`, outside every
  yardstick, until open question 3 is answered (`registers.SCENES_COUNT_AS`).
  `tables.public_text` is the only way into a fold. It returns None for a `p<id>` or
  `local` home, for a ledger row marked private, and when no library root is known.
  `targum tables sweep [--library DIR]` folds every public `annotation.json` that has
  no current count, running no annotator and spending nothing. `targum tables top
  --register R [--phrases] [--raw]` prints the commonest rows, leaving out the
  `weights.EXCLUDED` classes, names and numbers unless `--raw` is passed.
- The yardsticks (targum-internal#579, for #575): `targum tables snapshot` writes
  `yardstick-<register>-v<N>.json` for conversation, news, literature and the Bible
  (never scenes or the weekly): the commonest 20,000 content lemmas, each with its share
  of the list's running words, and the provenance by licence and tool. The files go to
  `/var/lib/targum/tables/` on the box and `~/.targum/tables/` elsewhere
  (`TARGUM_TABLES_DIR` overrides), never the repository. A register's list stands until
  the month turns (David, 2026-10-30), an unchanged list is never written twice, and a
  register under 50,000 counted words gets none yet. `--force` writes now. The nightly
  `targum-tables` unit runs it after the sweep. `level.coverage_on(register, known)` is
  the share of a list a reader's known words cover, None with no list.
  `level.coverage_days` gives the share before the word records began and each day's
  gain after, recomputed against the current list from `word.known_at`.
- Your Progress, "How much Hebrew you understand" (David, 2026-10-30;
  targum-internal#575): in the place of "Words you knew", the share of a fixed word list's
  running words the reader's known words cover, on a yardstick they pick: everyday
  conversation, a news article, classic literature or the Bible, each with its own
  percentage in the picker, news first for everyone. A yardstick with no list yet is left
  out, never shown as 0%. Week | Month, the line recomputed against the current list from
  the day each word became known, and nothing drawn before 30 October ("Counted since 30
  Oct."). "You know 87% of the words in a typical news article, up from 79% in August.",
  with what was read this month as one small line under it. Exact percentages.
  `/account/reading` carries `understand`. A language with no yardstick keeps "Words you
  knew". Russian strings are drafts.
- Topic tagging, the pilot (David approved 2026-10-30; targum-internal#605, epic #609).
  `scripts/tag_topics.py` tags Hebrew lemmas with up to two of 16 topics, or `general`,
  on Sonnet 5.5 and Opus 5.5 through the Batches API. It sends the lemma, its pointed
  citation form, its part of speech and its cached English gloss, never a sentence. The
  lemmas come only from the language tables (`topics.universe` over `Store.top`, with
  the new `Store.variants` for the part of speech), never from `word` rows or the gloss
  cache. `--cap` is hard: a batch is sent only when the most it could cost fits under
  the cap with what is spent. `--dry-run` quotes. A batch's id and every raw answer are
  written atomically to `~/.targum/research/topics/<run>/`, and the agreed tags go to a
  private topics file under `~/.targum/`. `--blind N --blind-out FILE` writes a
  stratified set with no model tags for ling-he to label. `targum topics share --person
  beginner|oleh|news` prints a synthetic reader's frequency-weighted share of each topic.
  It never reads a real account. Nothing on any page changes.
- Topic tagging, prompt 2 (David approved 2026-10-30, after pilot 1 scored 87% topic
  precision against ling-he's blind gold set, below the 90% gate). `topics.screen` leaves
  out, before anything is sent, a lemma counted mostly as a function word
  (`weights.EXCLUDED`), a number or a name over every register, a one-letter lemma, and a
  noun carrying a clitic ה, ב, ל or כ beside a bare noun the tables count as often
  (הפועל); each is listed with its reason in the run's `lemmas.json`. The prompt asks for
  the lemma's commonest modern sense and calls the gloss a hint, Religion & tradition and
  Science & technology take ling-he's definitions word for word, and words for people as
  such go to People & feelings. `topics.PROMPT_VERSION` is `prompt/2`, recorded in the
  run and the lexicon's version. `--from-run` asks again about another run's lemmas.
- The language tables keep growing on the box by themselves (targum-internal#587, David
  approved 2026-10-30). `deploy/targum-tables.timer` runs `targum tables sweep --library
  /var/lib/targum/targums` at 02:30 UTC, before the 04:00 backup, as targum and never as
  root, with `TARGUM_LEDGER` from `targum.env`. It runs at idle CPU and disk priority
  under a memory cap of its own (`MemoryHigh=600M`, `MemoryMax=1G`, no swap), so it can
  never push the service out of memory, and logs to the journal. Every deploy installs and
  enables it. The sweep reads `annotation.json` files and never ran a model; it now
  refuses to import one too (`tables.no_models`: torch, transformers, stanza, onnxruntime
  and the rest), so no later change to the fold can start a second DICTA beside the
  service's. The laptop's rows reach the box with `targum tables push`, which writes them
  with `targum tables export` and imports them over SSH as `sudo -u targum targum tables
  import`. The import is idempotent: a contribution id is a content hash, a row already
  there is left alone, and the newer of two counts for one text wins while the other stays
  as history. It refuses rows the box wrote, malformed lines, and any unit the box's ledger
  holds as private. `deploy/RESTORE.md` now says what `corpus.db` holds that no cache does.
- `deploy/REINGEST-TANAKH.md`, the step that runs after the next approved deploy
  (targum-internal#507 part 2): a read-only query for every Tanakh copy on the box whose
  verses carry no refs, then `targum refs`, a marked annotator name and `rebuild --words`,
  so OSHB reads it and readers' marks move with the lemmas. It says why deleting
  `annotation.json` would empty the page, what it costs (nothing but `--gloss`'s cents), and
  how long (about 25 minutes of re-rendering plus seconds a book). Counted on 2026-10-22:
  0 on the box, 13 on the laptop's `targum-out`.
- `voice_shelf.py --hint scene:turn=text` says how one turn's word is read, after the
  line's own pronunciation hints (targum-internal#566; qa's listening check, 2026-10-29).
  It is repeatable, held in memory only, and the scene files are never written. Only the
  direction and the automatic hints give way for it under the 180-character limit. A
  hinted scene counts as changed, so `--only` re-voices it, and only the hinted turn is
  bought: every other prompt is unchanged, and so is the key of every scene without a
  hint. A hint for a scene or turn that is not there stops the run before anything is
  bought. It re-bought 12 flagged lines for $0.03 on 2026-10-30.
- `targum align-subtitles <folder>` times each word of a video whose transcript came from
  its subtitle file (David, 2026-10-29: "Align on the laptop"; targum-internal#572). It
  runs the local forced aligner over the subtitles' own words, part by part, on the
  laptop, because the box has no torchaudio. It is free and takes about 2 minutes per
  8.5 minutes of audio. A word keeps its clock only if its letters scored at least -3
  (`subtitle_words.WORD_FLOOR`) and it landed within a second of its own cue. Any other
  word gets no clock, so the page lights nothing there rather than the wrong word. A
  line with no sure word keeps the part of its cue that its neighbours leave. It
  rewrites `audio/refined/` and the manifest, never the text. `targum rebuild --only
  p1/<name>` then rewrites that one reader. The Touring Israel interview's first three
  parts keep 3,242 of 3,602 words, and no line spans overlap.
- Pointed Hebrew in standard ktiv menukad, and four kinds of scene check from ling-he's
  audit of 2026-10-29 (targum-internal#563). `vocalize/menukad.py` turns full spelling under
  points into the standard spelling (חִיבּוּר → חִבּוּר, בּוֹקֶר → בֹּקֶר, and the menaked's
  mixed יֹופִי → יֹפִי): sixteen named rules, an exceptions list (הָיִיתִי, plural ־ִיִּים,
  consonantal vav, loanwords, qtilut nouns, cast names) and a lexicon. It is idempotent,
  prints every change, and `residue` names what it missed:
  `python -m targum.vocalize.menukad SCENE.json …` reads only, `--out DIR` writes copies.
  Over both scene sets it makes 1,191 changes, matches 1,153 of the audit's 1,156
  mechanical rows (the other three are cast names, kept on purpose), leaves 0 residue and
  keeps every exception (107 occurrences). The menaked can do the same at the source:
  `dicta.assemble(drop_matres=True)` drops the letters its head calls matres and keeps
  שָׁלוֹם and הוּא whole. Neither is wired into a scene yet, because a scene keeps one
  string and the reader's plain view is that string with the points taken off, so writing
  defective spelling into it would change the unpointed text too. `dialogue/checks.py`
  gains a 2fs final shva, a missing dagesh after the article, a dagesh where none can
  stand, Bit without its dagesh, ten homographs decided by the English (פֶּה for פֹּה,
  שָׁם for שֵׁם, צִיּוֹן for צִיּוּן …), and the speaker's gender on a present (אֲנִי רוֹצֶה
  in a woman's mouth) and the listener's where no pronoun says it (נִרְאֵית to a man,
  תָּבוֹא to a woman). Their kinds are `pointing`, `homograph`, `speaker` and `addressee`,
  so the B1 generator refuses on them. Together they find all 16 of the audit's P0s and 59
  of its 61 hand-read pointing findings; the two missed are judgements (לַקָּפֶה for an
  invitation, לְצָפוֹן said latsafon).
- Scenes keep two spellings (targum-internal#568). A turn's `text` stays the full
  spelling, which the plain cell, the voice, the taps and the audio clocks all read, and a
  new `pointed` holds standard ktiv menukad for the pointed cell. A scene without one has
  it derived by the normaliser at build, so the 127 scenes read correctly with no file
  touched. The build takes a scene's pointed cells from the scene itself
  (`dialogue/spelling.py`). A pointed line still in full spelling, missing a vav no rule
  removes, or out of step with its text word for word builds that scene without vowels
  and says why. Offsets cross between the two spellings by alignment rather than by
  counting letters: `vocalize.aligned_positions` in the build (pronunciations, the
  printed page) and `alignMap` in reader.js (taps, glosses, phrases, audio words). A test
  holds the two to the same answer. Over the 127 scenes: 2,397 pointed lines, 877 whose
  letters now differ from their text, 0 words landing on the wrong word, and 0
  differences between the browser's map and the build's. `spelling.repair` is where a
  generator sends `pointing` and `homograph` findings instead of back to the writer. The
  private writer keeps every turn's `said` (the Russian) and the scene's `named` and
  `glossed` across a rewrite, and stores both spellings. `python -m targum.vocalize.menukad
  --pointed --out DIR` fills `pointed` in scene files.
- `scripts/voice_shelf.py`, which re-voices the whole scene shelf with the #566 pipeline
  (David approved it 2026-10-29: 381 scenes, 5,198 turns). It stops at a spend cap
  (`--cap`, default $30), counted per bought turn with the director included and a
  cut-off request priced as an average turn. On a 429
  it reads the quota Vertex names and the wait it asks for, waits that out, and resumes:
  a per-minute limit in place, a stubborn one after `--pause`, and a per-day one (by its
  PerDay quota name, whatever its retryDelay) after the midnight-Pacific reset. `ru-` scenes get a Russian director brief and no Hebrew hints, and a
  speaker with a missing or wrong-gender voice gets the usual voice for that language.
  It writes `progress.json` after every turn and scene. `--dry-run` gives counts and a
  price: on the laptop's shelf, 267 Hebrew and 114 Russian scenes, an estimated $9.59 at
  today's lengths ($11.70 if reads run 25% slower), and about 10 hours at 3 s spacing.
  `voice_scenes.say` now hands every 429's quota to a callback and waits the
  retryDelay it gives.
- `scripts/speed_pass.py`, a read-only speed pass on the live public pages for design.md
  §14 line 5 (targum-internal#551, from builder-3's pass of 2026-10-28). It loads the
  landing, the Library, three text and scene pages, /about, /privacy and /terms cold on a
  throttled phone and an unthrottled desk, prints the largest contentful paint and holds
  the phone's to 1.5 s, with a 450 ms margin printed beside it as a warning; it exits 1
  when a page is over or records no LCP. Only GETs leave, nothing signs in, and its
  user agent ends in `targum-speed-pass`, which the visitor count now drops.
  deploy/README.md says when to run it: after a deploy that touches the public pages.
- `scripts/speed_pass.py` measures the signed-in pages too (targum-internal#552), as the
  box's test account and never a reader's (David's word to sign in from a script,
  2026-10-28). `--sign-in <link> --state <file>` opens a test account's one-time link and
  presses its button, the run's only POST; `--state` then loads home, Subscriptions, the
  signed-in Library and two readers (through `/open/`, which never builds), and under each
  line prints the server's time for the page, the main thread's, when the last fetch came
  back, and when the page's `<main>` was shown: home hides its main until its script has
  drawn it, so its LCP can be the footer's line. `--warm` measures a second load with the
  files kept, through DevTools' own interception, because Playwright's routing turns the
  HTTP cache off. The sign-out, which empties a test account, is refused whatever its
  method, and service workers are blocked so no request passes the guard. The sign-in
  runs under the same guard, letting through only its POST to `/account/enter`;
  `--expect <address>` stops before the press when the link names another address; the
  state file is created owner-only, and a `--state` path inside the checkout is refused.
- Your Progress has every §14 state pinned in a browser (targum-internal#471):
  `tests/test_progress_states_browser.py` loads the page signed out, empty, with a lot
  (5,000 words, 500 texts, 200 days), with the story failing and offline, at 1440 and at
  390 as a touch phone. Each must say what to do next, with its press where it has one,
  never scroll sideways, and throw nothing. The page itself is unchanged.
- The back office counts the beta's gate in one row (targum-internal#458). Under Each
  week's readers, **Since the beta, 2026-10-19** adds up every week from batch one's
  (invitations confirmed 2026-10-21, #460) with the same columns, so the go/no-go (#486)
  quotes one line, "A second text 3 of 6, Week 4 2 of 5", instead of adding weeks, and
  the alpha's readers before it stay out. A second text now has to come on a later day
  than the first day the reader read, not the day they were let in: somebody who signed
  in three days after the invitation and opened two texts that evening was counted as
  having come back. Its first day and Came back now keep the reader's local day and
  UTC stamps apart, so an evening west of Greenwich is one day, and a line under the
  table says what each column means. Read from the rows the store already holds; nothing
  new is kept.
- `deploy/harden.sh` does three more things (targum-internal#9). It puts Caddy in a
  systemd sandbox (`deploy/caddy-sandbox.conf`: the limits targum.service and the minter
  already carry, writable only in /var/lib/caddy and /var/log/caddy; Caddy scored 8.8
  EXPOSED in `systemd-analyze security` on 2026-10-28 against their 5.3). It is checked with
  `systemd-analyze verify`, Caddy is restarted, and `/health` is probed through it; on any
  failure the drop-in comes out again by itself. It turns off X11 and agent forwarding
  in sshd and leaves how anyone logs in alone. And it reports a reboot that has been
  waiting, with the date: the box has been running kernel 7.0.0-29 with 7.0.0-38
  installed since 2026-10-08. It never reboots. The minter unit's comment no longer
  claims a loopback binding: it listens on `*:4416`, behind two nft tables. No step that
  can fail under `set -e` comes before its own undo any more (qa on targum#967): Caddy's
  reload, restart, check and probe, sshd's reload, the wall's rollback timer and the
  swapfile's three steps each take their change back and stop. Nothing runs on the box
  until David runs the script.
- The back office flags sign-ups that might be fake (David, 2026-10-27;
  targum-internal#544). Eight flags, each a plain reason under the address, all read from
  what the store already holds: never confirmed after 2 days, confirmed within 10
  seconds, the same inbox as another address, a throwaway domain (a CC0 list of about
  9,960 domains vendored in `src/targum/disposable.txt`, never fetched), one of 5 or more
  sign-ups within 10 minutes, let in and never signed in, signed in and nothing done, and
  mostly digits before the @. Accounts and the waitlist take a "Possibly fake (2+)"
  filter and a Most flags order. A flagged row still waiting has a Turn off press, which
  sets it off without deleting it or writing to anybody and can be undone from the same
  row (schema 49: `waiting.turned_off`, `waiting.was`). An address turned off that asks
  again is sent nothing.
- A Hebrew beginner's one card on home is their next scene (David, 2026-10-27;
  targum-internal#545). A beta reader came back after a long gap and could not find the
  dialogues. A Hebrew reader who said aleph, bet or nothing, and whose measured level is not
  yet B1, now sees their next unfinished scene where home's single suggestion stood, with
  its picture and one line: "Start here" until a scene is under way, then "Your next
  scene". The order is scenes 1 to 100, 101 to 240, then the B1 conversations, and a
  scene they would follow 95% or more of from their own known words is skipped. Everyone
  else keeps the ordinary suggestion. The Library gains a Start here shelf in the same
  order and a Dialogues door among Browse by kind. Scenes 1 to 240 are one collection,
  Scenes, whose order is built from the scene numbers, so a new scene joins it without a
  new collection. A reader who said bet is a beginner too while nothing is measured, and
  /suggest no longer cuts the finished ids at 200, which could offer a finished scene.
- A named back beside the mark in the reader and Theatre (David, 2026-10-28;
  targum-internal#546). A beta reader got stuck inside a reader: the mark was the only way
  out and went to Your targums whatever page they had come from. Beside the mark, which is
  unchanged, the bar now names where the text was opened from, "← Library", "← <playlist>",
  "← Words", and goes back there; with nothing to say (a shared or typed link) it reads
  "← Your targums". Each desk page writes its name to the tab's own store as it is left and
  the reader reads it, so nothing is added to any address. The next section, a playlist's
  next item, the next scene, a reload and the browser's Back keep it. It is 44px with a
  visible label, fades with the bar and comes back the same ways, and is the first Tab
  stop, which brings the bar out. In Theatre the mark and the back stay at 55% while a
  video plays instead of vanishing. The reader is laid out to the screen's edges
  (`viewport-fit=cover`) and the bar clears the notch in the installed app.
- On a phone, Back closes Talk before it leaves the page (David, 2026-10-28;
  targum-internal#548). The sheet covers the page, and the phone's Back, or the swipe,
  left the page under it. Opening the sheet now adds one step to the history at the same
  address: Back closes it and the next Back leaves. ×, the dimmed page, the handle and
  Escape take that step back, so no step is left that does nothing, and a text opened from
  the conversation takes its place. A conversation opened from the search palette no
  longer adds a step of its own (the frame's address is replaced, not set). The desk is
  unchanged.
- Your words are one step from a text's word list, with the way back to the same place
  (David, 2026-10-28; targum-internal#547). The "Words from this text" panel ends in "All
  your words →", on a phone's sheet and at a desk. Your Words opened that way leads with "←
  Back to <text>, where you stopped", in Your Progress's place, and it opens the text at
  the sentence the reader was on, with the text's own back still naming where it was
  opened from. Opened any other way, Your Words is as it was. An address typed or pasted
  after a visit to the Library now opens a text with "← Your targums" rather than "←
  Library": a desk page counts as where a text came from only when it was left by a press
  (qa on targum#963).
- The back office shows each reader's credits (David, 2026-10-27; targum-internal#543).
  Accounts gain Credits this month, the same sum the allowance is held to, against the
  reader's allowance (Plan's for an admin), with the month's model spend in dollars
  beneath, and can be ordered by it. An address opens that account's page: this month and
  all time by kind (build, subscription, voice, chat, gift) and its latest fifty jobs by
  day, kind, credits, cost and stage, with no title or source. A job targum pays for now
  says so (`job.gift`, schema 48, written at claim), and a gift turn of conversation no
  longer settles its seconds onto the reader's month. Search ignores case in every script,
  so «дина» finds «Дина».
- The back office scales past a few hundred accounts (David, 2026-10-27;
  targum-internal#542). Accounts and the waitlist are pages of fifty with a search box,
  an order and Previous and Next, as a GET form and links, so the page still carries no
  script for them. Accounts open newest first and can be ordered by last active, words,
  texts or days; the waitlist stays oldest first, with those let in folded and paged on
  their own. Each row's figures and the thirty-day strip are counted for the accounts on
  the page only; Follow up, each week's readers, how far readers get and the headline are
  summed in the store instead of read row by row into Python, and Follow up names the
  oldest fifty with a count of the rest. Five indexes (`job(owner)`, `job(made)`,
  `waiting(asked)`, `person(made)`, `event(kind)`) are made on the next open. Measured on
  5,000 accounts and 200,000 words: under a second for the page.
- The nightly backup now copies the corpus ledger (`corpus.db`, targum-internal#162),
  which the ledger-only step needs before any stage stops writing its cache file. It is
  taken as a SQLite snapshot (never a file copy of the live WAL database), checked as it
  is taken, kept fourteen nights beside the others, and sealed and sent with the rest as
  `corpus-<stamp>.db.gz.age`. The backup unit names the ledger, `--ledger
  /var/lib/targum/corpus.db`. With no ledger switched on, the backup says so in one line.
  It mails the operator, while the rest of the night goes on, when a copy fails, when
  `TARGUM_LEDGER` is set and there is no file to copy, or when the unit and
  `TARGUM_LEDGER` name different files. `deploy/restore-drill.sh` decrypts the
  newest ledger copy after the database, checks it and counts its rows, and `targum
  restore corpus-<stamp>.db --store …` puts one back. Run it as `targum`; run as root by
  mistake, it gives the restored file to the folder's owner. A snapshot that fails partway no
  longer leaves a partial file for the sweep to count. Nothing changes on the box until
  a deploy carries the new unit.
- The corpus ledger's fill now finds texts at any depth (targum-internal#162). A laptop
  check of 2026-10-27 found it reading one level down: it missed the parasha
  (`parasha/read/<slug>/print`) and 604 texts three levels deep. Private or public is
  still decided by the top folder, so `p3/local/…` and `local/videos/…` stay private,
  and the build-time writer and account deletion use the same rule for nested folders.
  A text found at two depths is one text. Symbolic links are not followed. A `weekly:`
  source counts as `targum`, our own writing, in the catalogue or not (David,
  2026-10-27). A translation held in two copies of one text is recorded once per fill:
  the fullest among the public folders for a public text, or among the homes for a
  private one, so a second fill adds no history. A newer write at build time still
  replaces it. The build-time writer uses the same top-folder rule under the library
  root the server registers or the build's `--out` root. With no root known it treats
  any `p<id>` or `local` folder on the path as private, and a `document.json` linked from outside the library is not read. On the laptop library the fill went
  from 343 texts to 943, and the commercial export from 269 texts to 552.
- `targum build` and `targum weekly build` now tell the corpus ledger which library they
  write into (targum-internal#162), as `targum seed` already did: `./targum-out`, or the
  weekly's library. So the ledger applies the fill's rule to them. A text under
  `demos/olim/shelf/p1/`, or in a library that sits below a folder named `local`, is no
  longer recorded as private by the fail-closed fallback, and the export does not
  shrink. A command-line build into a folder outside `./targum-out` still fails closed.
- The corpus ledger's `texts` table (targum-internal#162, slice 1 of the plan on the
  card). Each source document gets one row in `corpus.db` with its source, its licence
  string, whether it is a reader's private import, and two export bits computed from David's 2026-10-08 rule
  (`licensing.export_terms`). Commercial export admits public domain, CC0, CC BY,
  CC BY-SA and targum's own writing (David, 2026-10-27). Research export also admits CC BY-NC and CC BY-NC-SA. ND texts, texts with
  no licence and readers' private imports go in neither. A licence corrected later keeps
  the old row as history, and so does a rule that now reads the licence differently.
  Which readers' homes hold a private import is kept apart from the row, current only,
  so a departed reader's home leaves every row, including texts another reader still
  holds. Account deletion removes the row when the text was theirs alone. Only `p<id>`
  and `local` folders count as homes. `targum cache ledger-texts`
  fills the table from the built folders and spends nothing. Ledger schema 3 only adds
  the table. Nothing reads it yet, so no reader sees a change.
- The corpus ledger's export bits now travel (targum-internal#162, slice 2). Every
  build writes its text's `texts` row as it runs. A build in a reader's home marks the
  text private to that home, unless the shelf already holds it. A build anywhere else
  marks it public. Each pointing and annotation row now carries its text's `exportable`
  and `research` bits, and a licence that changes restamps every row of that text,
  history included. A text with no row exports nowhere. Ledger schema 4 adds the two
  columns in place. The ledger is still off unless `TARGUM_LEDGER` is set, it never
  fails a build, and no reader sees a change. If another process holds the ledger's lock,
  a build waits at most 2 seconds for it, then goes on without the row.
- `targum corpus export <folder> --exportable` or `--research` (targum-internal#162,
  slice 3) writes the corpus ledger as a dataset: one JSONL file per table (texts,
  pointings, annotations and their tokens) and a datasheet listing every source,
  licence and tool with the row counts. Only current rows go out. A text leaves only
  when its bit is set, it is public, no reader's home holds it, and the licence rule
  asked again gives the bit, so a wrong bit alone exports nothing. Private imports,
  texts with no licence and ND texts are in neither export, and no account id is
  written. It reads the file `TARGUM_LEDGER` names, spends nothing, and refuses a folder
  that is not empty.
- The corpus ledger holds translations and their aligned pairs (targum-internal#162,
  slice 4; ledger schema 5). Every build, and every chapter bought later, records each
  rendering in its folder with each sentence beside its translation.
  `targum cache ledger-translations` fills the table from the `translations/*.json`
  files already on disk. Filling translates, fetches and spends nothing. A rendering
  targum made is under its text's licence, and a published one under the licence the
  catalogue gives it, or none. A machine translation is in the research export only,
  never the commercial one, because the model providers' terms bar using their output
  to train competing models (David, 2026-10-27); the datasheet says so. Its export bits
  are its text's and its own together, so translations of readers' own texts stay
  private. While a text is on the shelf, a reader's copy of it records nothing, so a
  partial copy cannot stand in for the shelf's.
  `targum corpus export` now writes `translations` and `pairs` too, asking each
  rendering's licence again.
- The cache can read pointings from the corpus ledger first (targum-internal#162, slice
  5), behind a second flag, `TARGUM_LEDGER_READ=vocalize`, which is off by default. A
  ledger miss, a locked or broken ledger file, or a ledger that is off falls back to the
  cache's own file, so a stage never runs because of the ledger. The ledger answers only
  while the cache file exists and only with a row at least as new as it, so a dropped,
  cleared or newer file always wins. Reads are read-only and never take the write
  lock. A build served from the ledger asks the vocalizer nothing and spends nothing.
- Aramaic's free groundwork for the Onkelos climb (David, 2026-10-25; ling-arc's plan,
  gaps G1, G8, G9). **A frequency list counted from the shelf's own Aramaic**
  (`annotate/aramaic_frequency.json`, `scripts/count_aramaic.py`): Onkelos, Jonathan, the
  Targums of the Writings and the Aramaic of Daniel and Ezra, 448,177 words in 43 texts,
  filed the way the annotator files them. The difficulty measure reads it, so an Aramaic
  text no longer measures 0: Onkelos's books come out at 9 to 13, Jonathan on the Former
  Prophets 11 to 14, on the Torah 16 to 20, the Latter Prophets 11 to 28, the Writings 14
  to 37, and the level map places them. `touchstones.aramaic_ladder` makes those families
  the rungs, Onkelos first, and Your Progress climbs them (design.md §12, "Aramaic gets a
  ladder, from our own counts"): each rung named in English and, as a draft for ling-ru,
  in Russian, Pseudo-Jonathan by its everyday name, each a chip without a link until the
  Library has a shelf for each body of Targum (design.md §12 now lists these rungs until
  the Talmud bridge and the daf have texts). The tables carry ling-arc's review: readings
  reordered and added, five more abbreviations, six more terms, four moves changed. The
  line blaming a missing frequency list is gone; until the catalogue's
  Aramaic rows are measured, part 1 says what any unmeasured language says. The card is
  untouched: a word of Onkelos still says it is not rated, and nothing is re-annotated.
  **The Talmud's abbreviations** (`closed.TALMUD_ABBREVIATIONS`, 373 forms from
  Mielziner's 1894 key, read off the page scans, with every full form and its sense) and
  **its argument terms** (`closed.TALMUD_TERMS`, 76, each with the move it makes:
  source, question, objection, answer, verdict, frame), with `abbreviation` and
  `argument_term` to look them up. Data only, for ling-arc to check; no surface reads them
  yet. Nothing spent.
- An older Hebrew says which it is, and the shelf floors count modern Hebrew (David,
  2026-10-25: label only; design.md §12, "An older Hebrew says which it is" and "The
  floors count modern Hebrew"). A revival, rabbinic or medieval Hebrew text is labelled
  «Revival-era Hebrew, 1890s» (the decade from the year in its byline, where it has one)
  on its Library card and See all row, its public page, its contents page, the top of
  the reader the arrival opens, and the rows `find_text` and `suggest_next` return (`era`
  and `era_of`), in English and Russian (the Russian is a draft for David's read). The
  shelves, the arrival's subjects and what `find_text` returns are unchanged. The stage
  floors and `targum stages` read the modern ladder only (`levelmap.split`); the Tanakh,
  revival, rabbinic and medieval Hebrew are counted per register under `registers` in
  `evals/shelf.json` and printed, held to no floor, and `--measure` counts the weekly's
  published editions too. Modern B1 is 53 of 90, so Hebrew's Beta is kept in
  `stages.KEPT`, reviewed by 2026-12-31, until the first generated modern B1 tranche
  lands. A reader built before this shows its label from its next render.
- design.md §12 carries David's Aramaic decisions of 2026-10-25, from ling-arc's research
  into taking a reader from no Aramaic to Onkelos and the Gemara. The climb comes first
  (Onkelos, its grammar, a bridge into the Talmud, then the daf). Aramaic gets a ladder
  counted from our own shelf, a Hebrew counterpart on the card drawn only from an
  alignment held to a floor, and a hard-spot list of seven. There are five lenses (state,
  suffixes, ד־ and ית, abbreviations written out, the argument's moves), a section for the
  daf laid out (targum-internal#194), and a new rule: "Aramaic is never written by a
  model". The three rules this reverses are marked where they stand. Nothing is built
  yet: Your Progress and the card are unchanged until each piece lands.
- Two runbooks for the box (targum-internal#482). `deploy/ROLLBACK.md` puts the previous
  build back with `rollback.sh` when the box kept its wheel, or by deploying its commit
  again from a worktree (the only way back until a second deploy with targum#876 has
  kept one), restores the pre-deploy
  database through SQLite's `.restore` only when the data is damaged, and says what a
  step back across an annotator rename costs in box hours. `deploy/INCIDENT.md` is the
  first ten minutes: who is told, the read-only checks in order, how to tell the box from
  a model provider from the network, when to roll back, and what never to do. Neither has
  run as a drill yet.
- A step back without a laptop build (targum-internal#482). Every deploy keeps the wheel
  it installed, with its constraints and extras, in `/var/lib/targum-deploy/wheels/<sha12>/` on
  the box (the last five), and `deploy/rollback.sh <sha>` installs one of them again as
  the service account, restarts and checks `/health`. It refuses a commit the box does not
  keep, and says which ones it does; with no commit it lists them. Each deploy appends
  `<utc> <sha> <who>` to `/var/lib/targum-deploy/deploys.log` (who is the laptop's account), and
  a rollback appends its own line. The catalogue a deploy replaces is kept as
  `/etc/targum/catalogue.json.prev`, and `rollback.sh` offers it back (`--catalogue`).
- `deploy.sh` copies the database itself before installing anything: as `targum`, with
  SQLite's `.backup`, into `/var/lib/targum/backups/targum.db.before-<sha12>-<utc>`, and
  stops the deploy unless `integrity_check` says `ok`. The last ten such copies are kept;
  the nightly ones are untouched.

### Fixed
- A desk page asks who is signed in once (targum-internal#484). The inbox, the language
  keys, the account's corner and the page's own script each sent `/account/me` for
  themselves, three to six times on a cold load, some waiting on each other. `keep.js` now
  sends it once and hands each a copy; a change of languages still asks again. Phone
  profile, median of 3: your account 1.17 s → 1.01 s, Progress 2.69 s → 2.36 s.
- Progress on a new device draws what the account brings in place (targum-internal#484).
  With nothing in the browser it waited for the account and then reloaded itself whenever
  the answer brought anything, so a reader signing in on a new phone loaded it twice. It is
  drawn where it stands now, as Your Words is. Phone profile, median of 3: 2.69 s → 1.35 s.
- Your targums asks what does not wait on the shelf as the page opens
  (targum-internal#484). The account's places, the subscriptions' new items and the
  Subscriptions tab's own list were asked once `/readers` had answered, a round trip each
  after it, and the places were asked twice, by home and by the shelf. They go out with the
  shelf now, once each, and the tab's list is not asked again by the page's own redraws.
  Phone profile, median of 3: Your targums 1.69 s → 1.57 s, Subscriptions 1.61 s → 1.44 s.
- /parasha paints at once (targum-internal#484). The scroll's photograph rode in the page
  as a `data:` URI inside a `<style>`, 151 kB gzipped of a 305 kB page, and a stylesheet
  holds the first paint until all of it has arrived. A series page's picture (the scroll,
  each cycle's manuscript) is now a file of ours, `/assets/<name>.<hash>.jpg`, kept a
  year; nothing is fetched from anybody else's origin and a reader still fetches nothing
  (design.md §12, 2026-10-22). Phone profile, median of 3: first paint 1.40 s → 0.74 s,
  Read 1.66 s → 0.96 s.
- The Library no longer carries its shelf (targum-internal#484). A first visit is sent the
  page whole, and whole it carried the catalogue inside it: 303 kB gzipped of a 479 kB
  page, all in front of the first card. The shelf is JSON files of ours now, one with what
  every shelf needs and one per language, kept a year. `library.js` asks for the common
  one and the language it opens on beside `/readers`, and another language's only when
  the reader moves to it. Phone profile, median of 3: Library as a first page 2.74 s →
  2.21 s, 549 kB → 402 kB (design.md §12, 2026-10-22). A fresh browser asks for the
  account's language first, which the page now names, rather than Hebrew's; and a move to
  a language whose file does not arrive keeps the shelf and the language on the page and
  says so in one quiet line, opening by itself when the connection is back.
- `deploy.sh` no longer writes as root inside the service's own folders
  (targum-internal#512). The covers' `mkdir`, the receiving `rsync` (`--rsync-path`) and the
  `sources.json` merge run as targum through `runuser`, and the root `chown -R` after them
  is gone, since the files now arrive as targum's. The merge follows no symlink: a planted
  `.part` is replaced rather than written through, and a symlinked `sources.json` or lock
  stops the deploy before the wheel goes in. The catalogue lemma index is read as targum
  and written by root through a `.part` in `/etc/targum`, so a symlink in
  `/var/lib/targum` can no longer have root copy another file where the service can read
  it. Pinned by `tests/test_deploy_thumbs.py` and `tests/test_deploy_lemmas.py`, which
  fail on the old script.
- A Tanakh text with no verse refs is refused rather than read by the wrong engine
  (targum-internal#507, part 1). The morphology (OSHB) is looked up by ref, so the shared
  Ruth, ingested before refs, had every verse read by DICTA under an annotator name that
  still said `oshb`. A build, a seed and a rebuild's re-annotation now refuse such a text
  with "This Tanakh text has no verse refs, so the morphology cannot read it. Run targum
  refs, then rebuild it."; seed and rebuild skip it and name it at the end, keeping the
  copy on the shelf. A build whose Tanakh text the morphology read less than half of says
  so by name. Re-ingesting and re-annotating the copies on the box is part 2, a deploy step.
- The Grammar tab no longer reports an uncaught "Failed to fetch" when its first ask
  fails before the page's last script has run (targum-internal#504). `grammar.js` handed
  `yours.js` a promise nobody had caught yet; served by address, the browser runs other
  tasks between the two files, so a reader offline met it as a browser fault, and the
  page-scripts browser test met it about one CI run in three. The promise is caught where
  it is made, and `yours.js` still draws the refusal from it.
- A deploy refused because a rebuild was still running had already installed its wheel
  and catalogue under that rebuild: the `targum-deploy` guard sat below the install
  despite its comment. The laptop now asks before it sends anything, and the box-side
  block asks again first, so a refused deploy changes nothing on the box.
- At a desk, in Theatre, the playlist foot is no longer laid out under the picture
  (targum-internal#505). It stands beside `main`, which Theatre hides, so it stayed under
  the fixed picture, out of sight, and a press on its Play in order went to the video's tap
  layer. Theatre now hides the foot too; the row under the picture carries the same switch
  and Next, the transcript view still draws the foot under the picture, and the end card
  still takes it in.
- A Hebrew verb's card says the binyan of the word tapped, and draws that binyan's table
  (targum-internal#508, ling-he's grammar/7 read). The word's row is its first occurrence's,
  so Gen 12:3 וְנִבְרְכוּ (nif'al) showed the page's first ברך, a pi'el. An occurrence in
  another binyan now carries its own (`binyanimHere`) and its own table
  (`paradigmsHere`). And no conjugation table prints a raw Wikidata item: the three forms
  the source never named (Q1305037, Q344 · Q500726, Q462367 on הלך and היה) are left out
  of their tables. Render-time only; no annotator rename.
- Subscriptions, design's B8 and B1 (targum-internal#475). Subscribe again on a channel or
  a podcast that was unsubscribed goes to the confirm page with its old cap chosen, so the
  monthly cap is said beside the press again, and the door refuses a one-press resume of
  one (409, with the confirm page's link). A series or a topic, which is free, keeps its
  one press. An unsubscribed one draws no cap or mail card, and says "You unsubscribed on
  {date}." in its head. A fault is no longer told as data: a 502 on the tab says "We
  couldn't load your subscriptions." with Try again, not "You haven't subscribed to
  anything yet."; signed out, it says to sign in, with Sign in; and on one subscription's
  page only a 404 says we couldn't find it.
- Listening's finish, design's eight polish items (targum-internal#474). Play on and Play in
  order were one setting under two names and two drawings: both say "Play in order" and
  are the same switch. An empty Saved page heads its line "Saved by you", not "Saved
  automatically" beside "Saving automatically". Your targums' four tabs fit a phone in
  Russian. Deleting a playlist says "Deleted {name}." on the tab, and only after this tab's
  own Delete: the link carries the id, the name comes from a note the press left, so a
  crafted link says nothing. A screen reader hears a
  playlist's name and count apart in the sheet and the menu. Recent texts' 3, 5 and 10
  and the playlist switch are 44px across under a thumb. From targum's known share keeps
  to one line at a desk. Offline, the tab says where the saved playlists are, in one
  quiet line instead of a second fault, with its link underlined, and asks again when the
  connection is back. A length keeps its number and unit on one line ("25 min").

### Changed
- /connect and the approval page's copy, ling-en's pass on targum-internal#473 (the page
  lines; the four connector prompts are #848): the chat scope's second line is a sentence
  that says you confirm on targum, since /connect and Your account share it with the
  approval page;
  a credit is about a minute of audio or video; Your account by its name; subscribe, not
  follow, and news as links; we get a text ready, not "nothing is made". Russian twins
  drafted for ling-ru.
- Your Progress's Level v3, the back end (targum-internal#561; design.md §12, "Your level,
  v3", David 2026-10-29). A Native text is placed on B2, C1, C2 or Past C2 by the
  vocabulary it needs: the frequency rank that covers 85% of its ranked running words
  (calibrated on the built library; 95% put 10 of 11 Hebrew Native texts past vav), read
  off the lemma index beside the catalogue, against the ulpan's thresholds. French, Russian
  and Italian Native texts stay on B2 until the European scale has a ruler.
  It runs locally, stores nothing and spends nothing; a text the index has not counted
  stays on B2. `text_level` and `cefr_rows` move together, `B2+` stays as an alias for the
  four (old Library addresses open, and the stage floors still read B2 and up), and the
  Library answers `#see/level/C1` and the others. `/account/story` sends, for each ladder
  row, whether the reader's words reach it and the exact words to go if not, and on the
  rung the exact words to the next one ("637", from the one function, so C1's row equals
  the card's): the weighted gap over the average weight of the words marked known in the
  last 30 days, rounded up to a whole word and no further. Week one gets the words to
  aleph. `/account/reading` sends day buckets per language in the time zone the page
  names (`tz`), from the rows' own times. Every `.seg` reaches 44px under a thumb.
- Your Progress's Level v3, the page (targum-internal#561; design.md §12, "Your level, v3",
  David 2026-10-29). No visible heading; a hidden h2 names the part. The card is the level:
  the ulpan letter alone with its geresh at the page title's step, in a carried 600 cut of
  Noto Sans Hebrew's letters (2.8 kB, `scripts/hebrew_letter_face.py`), "About B2" beside
  it, a bar toward the next rung, "637 words to ה׳" exact, and "Show texts you can read
  now". French, Russian and Italian lead with their CEFR level. The ulpan explainer and the
  foot line are gone. Texts by level runs A1 to C2 and Past C2: covered rows say Easy for
  you or Next and "{n} you can read now", rows above say "{n} words to go", and a row with
  no texts has no chevron. Week one keeps the bar and the words to aleph, and its button
  says "Start learning". Words you knew draws by Day, Week or Month (`.seg`, the coarsest
  view with two points first, the choice remembered), says an exact percentage ("In
  October you knew 91% of the words you read."), is one tab stop with its points said by
  the arrows, and has no footnote. At a desk, two even columns.
- Your Progress's first part is Level (targum-internal#553; design.md §12, "Your level
  leads with what you can read", 2026-10-28). Its rows are the texts' own levels,
  Beginner · A1, A2, B1 and B2 and up (`levelmap.text_level`), each "Easy for you", "Your
  next step" or "Not yet" with "N you can read" counted by the Library's Read it now rule.
  The card leads with the hardest level you can read on your own, the next step and "Show
  texts at your level"; week one says where to start and names no level. No percentage is
  drawn in the section. One foot line gives the measured ulpan or European level, with a
  thin bar toward the next rung and no numbers. The Library filters by a text's level:
  `#see/level/<level>` and `#see/now/level/<level>`, a chip that clears it, and its
  shelf rows carry each text's `cefr`, so a row opens exactly the texts it counted.
  "Conversations" replaces "Dialogue" on the Library's door and Kind filter, rows, home's
  cards and the reader's list; ids and addresses are unchanged. The step labels lose
  their numbers. English and Russian as ling-en and ling-ru read them, approved by David.
- A public text page, the four legal pages and /about ship only the CSS they use
  (targum-internal#550). They carried all of shared.css and reader.css, about 315 kB inline,
  for a few dozen rules; they now load `public-page.css`, 2.8 kB, which
  `scripts/public_page_css.py` writes from those two sheets. Ruth's page went from 308 kB
  to 113 kB of HTML, /about from 330 kB to 135 kB and /privacy from 326 kB to 131 kB,
  before compression. Nothing looks different: a browser test computes every element's
  style on those pages with the file and with the two sheets, at 390 and 1440, light and
  dark, and requires them equal, and another fails when the file falls out of step with
  the sheets it is written from.
- Your account's finish polish (targum-internal#469, design's polish 1, 3–7 and 10):
  What's connected is drawn with nothing connected, with one quiet line and Connect an
  app. Every date is the day and the month in full, the year only when it isn't this
  one, and joined by a no-break space so it never splits at the end of a line (the day
  the credits come back too). The page's quiet lines are one note at §13's meta size in
  ink-soft. Prompts and Telegram chats are rows like the languages, a long prompt held to
  two lines, which opens on a press and closes on another. With plans on, a Free word
  list past nine in ten of its cap says how many more fit, with See plans beside it and
  not in the card's head as well.
- CI cancels a branch's or a PR's run when a newer push to the same ref arrives, so a
  round of fixes queues one run. Master's runs are never cancelled, because a deploy
  may skip the suite only for a commit CI passed there (`TARGUM_CHECKED`).
- Russian's badge says Alpha, to match its card (David, 2026-10-21). It is kept there by
  decision (`stages.KEPT`, reviewed by 2026-11-30): Russian is short only of the
  read-through of ten texts on record, and the stages test prints that on every run.
  design.md §12, "Russian wears Alpha while its read-through is done".

### Fixed
- Your Progress takes the rest of design's finish-bar polish (targum-internal#471). The
  words-by-week chart keeps this week at the end edge and names its first and last week
  under the columns, never in a box narrower than the dates, so one or two weeks' dates
  stay inside the card on a phone in Russian. The period chips are tinted pills at the control size. A story's step
  is §13's label. The Upload row stacks its aside under the term on a phone. A reading
  point focuses with a round ring, and a chart's tip goes under its point where there is
  no room above it.
- A page printed in Russian carries the chrome's Cyrillic cut, as a desk page does, so its
  own words are set in one face (qa on targum-internal#476). The fonts README cuts the
  subset in a scratch folder, not the checkout.

### Fixed
- The Anki deck's follow-ups from qa on #854 (targum-internal#496): a deck that stops at
  the sounds set aside for it says so ("We stopped at the sounds we'd set aside for this
  deck"), the cap line says "used", a deck whose voice is still working is never thrown
  away (so a second deck cannot start beside it and pass the month's cap), one stuck
  "making" for six hours with no job working is, each sound is counted as it is made, and
  the decks are walked under their lock.
- Russian's surfaces, design's four blockers (targum-internal#476). A page in Russian
  carries Source Sans 3's Cyrillic subset beside its Latin one, so a line is set in one
  face (design.md §13, "Russian is carried too"); a page in English pays nothing, and a
  reader carries the upright alone. The arrival no longer offers Torah and Judaism to a
  reader learning Russian, Italian or French. A language with no shelf (Yiddish) is one
  card that says so, with Upload and what works for it, not a search over nothing. The
  word card says what ignore is for ("Ignore is for names and numbers."), in every
  language, not in a title alone.
- The daily mail, from design's pass (targum-internal#470). A subscription named in Hebrew
  is drawn in Hebrew, right to left, in the Hebrew face, not as a capitalised English
  label, and a row's tile letter says its language. The whole row is the link, not only
  its title. The unsubscribe links have room round them on a phone, and the foot's links
  stand on their own line there. A one-item subject isolates the name as well as the
  title. A busy day draws thirty rows and says how many more are in Your subscriptions,
  so Gmail never clips the foot. The ready mail says hours past an hour ("3 hr 5 min"),
  and the card keeps its 14px corner on a phone.

### Fixed
- Listening's finish (targum-internal#474), design's nine blockers and ling-en's lines.
  Your playlists and a playlist's page say they are loading, and past three seconds that
  it is taking longer, with Try again; a fault is the shared panel with Try again, and a
  server that failed is no longer told as one that cannot be reached. A failed text says
  "Remove it, then add it again." A Russian reader's playlist foot is in Russian however
  fast the list answers. What the grip and Play in order do is said on the page, not in a
  title alone. The add sheet holds the focus and gives it back. A playlist row's title,
  the way back, Add from…, the sheet's × and the Listening view's position answer a thumb
  over 44px. A title still getting ready says its language. The lines either side of the
  one being said in the Listening view are drawn in soft ink, not at 38% opacity.

### Fixed
- The press that makes a playlist says "Create", not "Confirm", in the New playlist form
  and the Add-to-playlist menu (David, 2026-10-21; targum-internal#474).
- A library row filed without a picture is caught, and every picture in `thumbs/` says
  where it came from (targum-internal#429, slices 2 and 3). `targum thumbs --dry-run`
  names the rows left with only the letter tile and ends on "N rows without a picture",
  after the counts by origin (own, drawn, tile, overall and by language); `deploy.sh`
  prints that count before the covers go. All 152 tile-only rows of 2026-10-21 were
  filed after the October drawing, which is what this stops recurring. A drawn cover now
  writes its line in `thumbs/sources.json` (`from: drawn`, the model, the day) when it
  is drawn, under a lock, and `targum thumbs` writes one for any picture still without,
  dated by its file and marked `backfilled`. The laptop's 993 drawn pictures (927
  library covers, 66 chapter and upload covers) were written in this way, with no
  drawing and no spend: 379 own, 927 drawn, 0 tile. `deploy.sh` now merges
  `sources.json` into the box's rather than copying over it, so the lines the box writes
  for its own upload covers stay, under the lock the box's own writers take. A picture
  that belongs to no library row (a laptop upload's cover, a retired row's) no longer
  goes to the box, file or line: the box has its own uploads, and a laptop one with the
  same name would replace it.
- A word on a portion page answers sooner on a phone (targum-internal#409). The two faces,
  the player and the data behind Rashi's words now come after `reader.js` (Rashi's lines
  are in the page from the start; his words answer once their block arrives). The first
  tap on slow 4G with a 4x slower CPU, on pages built with their recordings: Bereshit's
  first aliyah 2.14 s to 1.39 s, Ki Tavo's sixth 2.30 s to 1.74 s.
  `scripts/measure_tap.py` takes the figure.
- The portion's PDF press says more than "Preparing PDF…" (targum-internal#409): past
  three seconds it says "Still making your PDF…", and offline it says the PDF is made on
  targum and needs a connection rather than "try again in a minute". On the reader's ⋯
  and on the series page, in English and Russian.
- Your Progress, design's four blockers (targum-internal#471). The month line's and the
  time figures' notes are quiet lines under them, not titles a phone never shows, and
  "learned on targum" has no tooltip. Until the account answers, part 1 says "We're working
  out where you are." and What next says nothing false; a story that cannot be reached says
  so with Try again. What next draws each word's meaning in the reader's meaning language.
  Its presses, and the fault panel's Tell us, reach 44px under a thumb. And from the
  polish list: no Practise press with nothing to practise, numbers grouped as the page's
  language groups them (11 385 in Russian), and a time figure kept on one line.
- Russian interface strings from the ling-ru audit (targum-internal#476), drafted for
  David's read. The case lens says «падеж», not «регистр» (letter case). Two hints said
  «нажмите Continue» over a button that reads «Продолжить». `add.spoken.ours` no longer
  promises a spend the English does not. A word's levels have one set of names on the card, the lists,
  the keys help and Your Words («едва знакомо / осваивается / почти знакомо / знакомо»);
  the landing demo's two buttons speak in the reader's voice («Знаю», «Осваиваю»). The foot buttons are Russian
  («Готово и отметить…»). Counts that came out as «342 слов», «в 21 строках» or «из 21
  глав» are said with a colon instead, and a one-form that also counts 21 carries its
  number («Прочитать {n} страницу»). `serve.give-a-link` has its Russian.
  `progress.reading.note` says words known *as of* that day. A phrase is «фраза»
  everywhere (David, 2026-10-21), and the books of the Bible are named in the Jewish
  Russian system: «Берейшит», «Шмуэль I», «Млахим I», «Диврей а-Ямим», «Теилим»
  (David, 2026-10-21), and the first portion is «Берейшит» like its book. The 24 missing `.other` plural forms are filled for fractional
  counts.
- The Russian portion page frames a Russian reader (QA, 2026-10-05). A reader's own
  words and the column it opens on are written in when it is built, in its first
  rendering's language, so `/parasha/bereshit?lang=ru` framed the English one: Listen,
  Chanted, "0 of 99 known" and the English beside the verse. `targum parasha build` now
  builds a reading with a Russian rendering twice (`parasha.build.ALSO_IN`): `reader/`
  as before and `reader-ru/` with the Russian first, served at
  `/parasha/read/<folder>-ru/reader/…`, whose recordings are the first build's and are
  not kept twice. The Russian page frames it, and its week list, next Shabbat's offer and
  print link stay in it. The haftarot have no Russian rendering and keep the reader they
  have. The companions, the sound's name and its credit line, and the bar's name beside
  the Hebrew are said in the reader's language. **The corpus has to be rebuilt and
  shipped for the box to have the Russian readers**; until then the Russian page frames
  the English one, as before.
- The Russian portion page says the book («Бытие», not "GENESIS"), «читают в субботу»
  rather than «читают Shabbat», and every portion's name in Russian («Берешит»), from
  `portion.name.<slug>`. A language pressed for (`?lang=ru`) rides on the links that stay
  on the parasha pages. The credit names the Russian Torah (Gerstein and Gordon, 1875)
  where the frame shows it. «· читать» on a part read this week is «· прочитано», and the
  haftarah is «Гафтара» throughout.
- Download PDF on the portion page says «Готовим PDF…» / "Preparing PDF…" until the file
  arrives, and the one-sentence refusal under the button if the box cannot make it. With
  no script it is still a plain GET form.
- The reader's findings from the live QA pass of 2026-10-05, with Rashi kept on by
  default and at full length (David's call):
  - **Listen keeps the verse being chanted on screen.** The follow-along centred the
    whole verse-and-Rashi block, which put the Hebrew off the top of the window; on pages
    it never turned to the verse's page at all. It now turns to that page
    (`TargumReader.turnToPair`) and brings the verse's own Hebrew line into the top third
    of the room, on pages and on a scroll.
  - **No line stands under the page controls.** A verse taller than the page could not be
    split, so it ran on under the arrows, "1 of 19", the words tab and the player. Such a
    verse is now cut across pages between two of its lines — the verse and its
    translation on the first piece, the commentary carrying on over the next — and the
    foot of the text (Done, the credits, the pager) takes a page of its own when the last
    page has no room for it. A relayout keeps the reader on the piece they were reading.
  - **The sheet printed from any page is the reader's view.** The print press read the
    vowels and te'amim off the first verse's cell, hidden on every page but the first, so
    a sheet asked for from page 4 came out bare; it reads the reader's own state now.
  - **On a phone every press of the bar stays on the screen while the voice plays** (⋯
    was at x=373–417 on a 390px window): the voice's line gives way first, then the
    title. And the bar steps back after a tap on Listen: a touch is no longer taken for
    a pointer resting at the top, and a touch's leftover `:hover` no longer holds it out.
  - **Chanted → Spoken while playing goes on playing**, from the start of the verse it
    was on, in the other reading. Paused, it stays paused.
  - **Download PDF in the reader says "Preparing PDF…"** on the press while the box sets
    the sheet (five or six seconds for a portion), then saves it under the box's name; a
    refusal is the box's one sentence under the choice.
- A level pressed on a word's card (1, 2, 3, known or ignore) leaves the card beside the
  word while it lingers and fades (targum-internal#420). The card was rebuilt against
  the span the redraw had just replaced, which has no rectangle, so it jumped to the
  page's top-left corner and lost the lines read off the word (its pronunciation, its
  form). The card is now rebuilt for the word's new span, found in the same cell at
  the same place (`holdWord`), and keeps its inline start (`showCardInPlace`). The
  keyboard's levels find the word the same way, rather than the first word in the
  verse with its lemma.
- While a voice plays, a line under the pointer no longer wears the band of the line
  being said: it takes a 1px rule outline instead (`body.voicing`, design.md §8).
- The PDF's foot sets the mark and the address on one line, centred on each other
  (targum-internal#415). The mark was a margin box's image, which sits on the text's
  baseline and stood above the address; the foot is now a running element (`.foot`,
  `content: element(foot)`) laid out with flex, and the address no longer wraps.
- A long meaning over a word wraps to a second short line instead of widening the word's
  slot and spreading the Hebrew line apart, and a meaning keeps up to 26 characters
  (it was cut at 16: "something…" is now "something waited for").

### Changed
- Your account, to the finish bar (targum-internal#469): ling-en's twenty lines (credits
  are "of audio or video", the export holds chats and not uploads, Delete says what goes at
  once and that we email when the rest is gone, and the plan and languages rows say what
  they mean), and design's eight blockers. A slow account says "We're getting your
  account." and, past three seconds, that it is taking longer, with Try again; an account
  that cannot be reached, or a reader offline, is no longer told to sign in, and the corner
  keeps the initials it held. A sign-in refused for an account inside its seven days now
  shows the server's sentence, the one way to keep it. Nearly out and out say what still
  works and when the credits come back. Delete ends on a card that says what happened,
  focused and heard, with Go to targum, and no redirect on a timer. Export says when it is
  done and when the session has gone. Selects and fields carry the 2px focus ring, which a
  brand test now holds against any focus wash, and four small controls reach 44px under a
  thumb. Every line the page says back is a status.
- Every mail's copy, from ling-en's pass (targum-internal#470): the sign-in mail no longer
  tells an unknown address its account is unchanged; the invitation names the button and
  carries its Claude and ChatGPT link as a link of its own rather than escaped text; a link
  saved on the front page and got ready on targum says so in its foot instead of "your text took more than a few minutes"; the
  digest is named "Weekly News Digest" over its dated masthead, its button says "Read this
  issue" and each level says "If you know {n} words"; the subscriptions mail says the cause
  before the instruction; and the deleted-account mail takes its days from the grace period
  and no longer says nothing remains before naming the backup that still holds it.
  "Uploaded by you" stays (David, 2026-10-21).
- The connector's four prompts are said in the reader's own words (targum-internal#473,
  ling-en's plain versions). A host puts each into the chat as the reader's message, so
  "Call find_text, then find_text with where set to mine" came out of the reader's mouth.
  The tools are still named where the model reads them: in each prompt's `needs`, in the
  tool descriptions and in the server's instructions. Merged before the live check, on
  David's word (2026-10-23): it follows the deploy, in Claude and ChatGPT, to show each
  prompt still reaches its tools.

### Added
- A podcast episode a reader adds keeps its feed's artwork as its picture
  (targum-internal#429, slice 4). The item's `itunes:image`, else the show's (`itunes:image`,
  RSS's `<image>`, Atom's `<logo>`), is fetched once on the box at build time through the one
  outbound door and kept as the reader's own `thumb.webp`, served only to them like any
  upload's cover. It is read no further than 5 MB, must decode as PNG, JPEG or WebP and be at
  most 6000 pixels a side, so an SVG or an error page is refused. Where it came from is
  written in `thumb-source.json` beside it. A feed with no artwork keeps the letter tile, and
  an episode's audio is no longer fetched as a page to look for an `og:image`.
- Your Words' Anki export carries each word's sound (targum-internal#496, a beta reader's
  ask). The deck is an `.apkg` built on the server (`targum.anki`, Anki's schema 11),
  replacing the browser's text file, which could not carry media. A word with no clip yet
  gets one the way a Hear press makes it, a targum gift under one claim per export, kept
  by the word, at most 5,000 words; a word without a sound still imports. The page says
  how far the sounds have got, and falls back to the text file, without sound, if the
  server cannot.
- Your Words plays a word's sound from the list (targum-internal#498, a beta reader: "And
  be able to play the sounds here too"). Each row, and the word's card on the page, carries
  the reader card's Hear: the voice's clip from `/say-word`, which targum pays for and
  keeps by the word, so a word anybody has heard is free after. Only in the languages the
  voice reads (Hebrew, French, Russian, Italian) and only on a served page.
  `TargumVocab.hearButton` is the shared control.
- Governed prepositions are declared modern-only (targum-internal#454). The spot reads
  the stored syntax, and Biblical text has almost none: 199 of Genesis's 20,753 tokens have
  a parse. So `targum stages` now says "modern only, not Biblical" with that reason, the
  practice offers no Biblical sentence for it (`practices.VERSION` 4), and a Biblical page
  draws no prepositions lens. No rename and no rebuild: the lens follows each page's next
  render.
- Your Words' "Met in" opens the text at the word (targum-internal#497, a beta reader:
  "link the full text here … context is king"). "2 texts" is a press that lists the texts
  under the row, finished latest first, eight at most and "And 3 more texts."; each opens
  its reader at the line the word first came round in, with the word marked in the
  practice card's teal ring. `/account/met` answers it off builds already on the machine
  (`meetings.texts_lines`), nothing fetched and nothing spent.
- More verbs find their conjugation table, and fewer find the wrong one
  (targum-internal#307). A pi'el written plene finds its pointed lemma (דיבר is דִּבֵּר's),
  and a root with its binyan finds its verb (שלך in hif'il is הִשְׁלִיךְ). An occurrence's
  binyan now has its say everywhere: a plene word of another binyan gets no pi'el (ניתץ
  tagged nif'al), one candidate in a binyan other than the occurrence's is refused (בוא in
  hif'il no longer draws בָּא, "came"), and where the letters find only another binyan the
  root's verb in the right one is used (עלה in hif'il is הֶעֱלָה, לחם in nif'al נִלְחַם). A
  verb the source holds twice is one candidate, so קיבל draws its table. Render-time only.
- `grammar/7`, an annotator rename and so a scheduled re-read (targum-internal#491, #494,
  #490). A lemma that shares none of its word's strong letters is refused, so לטחון is
  no longer "slipped" and לעבוד no longer "enslaved"; the word stands in, as where DICTA
  declines. An active verb is no longer filed under its nif'al: ויאמר, אמרו and לעשות are
  אמר's and עשה's, while a nif'al that spells itself (נכנסתי, להיכנס, and the future of an
  א- or ת-first root, תתפס, אאסף) keeps it. A pointed future is read by its marks, and only
  a qal is mended: a hif'il or pi'el future keeps DICTA's lemma rather than becoming
  "gathered". A present is filed under its past (לוקחים is לקח's, הולכים הלך's, חוגגים
  חגג's), and a pointed מוֹצֵא or מוֹכֵר is מצא's or מכר's where מוּצָג stays a hof'al. The
  seller mend reaches a verb again. A nif'al spelled before its root gets its binyan, so
  965 bare נאמר tokens draw a table. Marks follow the moves through the #141 lemma
  migration when a text is opened, and since this change a weekly portion and a day of a
  cycle carry their books' moves too (`moves.gathered`), so a mark made on a /parasha page
  is not stranded by the re-read.
- `oshb/7`, in the same re-read (targum-internal#454): a Biblical noun or adjective in the
  construct state says so from Open Scriptures' state letter, so the card's construct line
  reaches the Tanakh (בִּימֵי, בִּשְׂדֵי); not a suffixed noun (בָנָיו), a proper noun or the
  Aramaic emphatic. Scored by `scripts/eval_construct_state.py` with a floor, and the
  construct spot claims both registers.
- `phonikud/3`, in the same re-read (targum-internal#454): a pointed modern segolate is
  stressed on its first syllable where no accent places the stress, from ling-he's rule
  (`annotate/segolate.py`): כֶּסֶף is kˈesef, בַּיִת bˈajit, רַכֶּבֶת ʁakˈevet, where phonikud
  said every one on the last. Scored on the Tanakh against the accents
  (`scripts/eval_segolate.py`, `stress-rule/2`). And a suffix that holds the stress back,
  from the pointing and the word's class (targum-internal#500, `annotate/suffix_stress.py`):
  אָמַרְתִּי is ʔamˈaʁti, שֶׁלָּנוּ ʃelˈanu, אֵלֶיךָ ʔelˈexa. The annotator now asks a reading
  per form and class, since בָּנוּ "in us" and בָּנוּ "they built" are pointed the same, and
  neither rule runs on a word that carries accents, so no Biblical text's stress changes.
  Scored on the Tanakh as `stress-rule/3`. A segolate the rule placed is no longer
  "inferred" on the card: ling-he's hand-read modern gold (`evals/stress-modern-gold.tsv`,
  300 firings) scores it at 0.9899 with הַחַג and שֶׁאֶת listed, and the stress spot
  claims both registers with a floor each. The suffix rule's words stay "inferred" until
  its modern gold is read. The shelf survey (`versions.current_name`) now
  carries the pronouncer's version, so a phonikud bump shows as behind; `rebuild --words`
  already compared whole names and re-reads the pronunciations either way.
- `/aliyah`, a front door for olim (targum-internal#385). A short page beside the front
  door, which does not change: "Learn Hebrew from your own life in Israel", the four
  moments that send an oleh looking, four lines of everyday Hebrew from the bank, the
  school, the building and the clinic, the places targum reads, six questions and the
  waitlist, drawn on the rebuilt front door's parts.
  No Torah section. English and Russian, in the sitemap, and there only while the front
  door is open. It is drawn from the front door's parts and carries no script. design.md
  §12, "Olim have a door of their own".

- Next Shabbat's portion at the end of the last aliyah (targum-internal#416): "Next
  Shabbat · נֹחַ · Noach", linking that portion's reader, and under it "You already know
  109 of its words", counted against the reader's own word list (`targum:vocab:he`) by
  the header's rule, known meaning marked known. The haftarah's end carries the same
  offer. `GET /parasha/next/<folder>?schedule=` (`parasha.build.following`) says what
  follows by the calendar on the schedule the browser keeps (`targum:schedule`, as the
  Weekly portion shelf does), from the occurrence nearest this Shabbat, so a doubled
  week, a festival Shabbat and the weeks Israel and the diaspora part are as read; where
  the calendar is silent the cycle answers and the year wraps. The next portion's words
  go only to a reader with a word list; signed out, or with nothing known, the offer
  stands without a count. `targum parasha build` now writes each portion's words beside
  its reader (`read/<slug>/lemmas.json`, names and numbers left out); a corpus built
  before this offers the portion without a count until it is rebuilt and shipped. On a
  portion's last aliyah the library's own "Up next" pick stands down for it.
- Download PDF on a portion (targum-internal#415): the week's shnayim mikra sheet, set on
  the box when pressed, from the ⋯ menu of a portion's reader and a button on its
  `/parasha` page. `GET /parasha/<slug>.pdf` sets what `targum export mikra` sets: the
  portion beside Onkelos (the reader's language where the shelf has no Onkelos yet), the
  haftarah, and for a reader signed in the words they looked up this week, or kept.
  Signed out, the sheet has no list and is kept on the box under `<cache>/sheets` by the
  hash of its page; a reader's own is set each time and kept nowhere. Two at a time, each
  in a process of its own that is stopped after three minutes; any refusal is one
  sentence and the reason goes to the log. `targum parasha build` now keeps what the
  sheet is set from beside each reader (`read/<folder>/print/`: the cut text, its
  renderings, its pointing and the forms its words are cited in, not the annotation), so
  **the corpus has to be built and shipped again** for the PDF to work. The box takes the
  `print` extra on the next deploy, and needs Pango, which `provision.sh` now installs
  on a fresh box: on the live one, `apt-get install -y --no-install-recommends
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core fonts-urw-base35`
  as root. The sheet prints the view the reader was on (companions, vowels, te'amim,
  beside or under, marks, this aliyah or the whole portion and the haftarah), and
  `/parasha` asks for those in a row of boxes; it carries the lockup over the first title
  and the mark and its address at every foot, on §4's paper; and the words a reader is
  learning are lit with their meaning just above them, or signed out, the rarer words'
  meanings. The build keeps the words and meanings for that beside each reader
  (`print/words.json`, `print/glossary.<lang>.json`). `targum export mikra` takes the same
  view (`--with`, `--aliyah`, `--haftarah/--no-haftarah`, `--gloss/--no-gloss`).
- Two readings on every aliyah, chanted and spoken (targum-internal#412). A portion's
  section carries the PocketTorah chanting attached to the portion and Rabbi Dan Be'eri's
  plain reading of the book, with a Chanted / Spoken switch in the bar, kept per browser,
  and both readers credited. Be'eri reads a chapter to a file, so an aliyah's verses are
  cut out of each chapter they fall in and joined into one file (`recording/splice.py`,
  `audio.tools.splice`), kept in the cache by what it was cut from; an aliyah across a
  chapter hears both. Both files ride beside the reader in `reader/audio/` rather than
  inlined, and `/parasha/read/…/reader/audio/*.mp3` serves them with ranges. Verse by
  verse for both. Asked for by the parasha build only (`render(recordings_beside=True)`):
  every other text keeps its one recording inlined, exactly as before. A portion with no
  chanting yet has the plain reading alone, and so does a haftarah.
- A Weekly portion shelf in the Library (targum-internal#411): this Shabbat's portion
  first, in a wide card that says it is this Shabbat's and when, then the year onward
  from it and round, each card opening the portion's reader. Above the list and on the
  Hebrew shelf only. `GET /portions` (`parasha.build.shelf`) says the cycle and which
  portion each calendar reads this week, and the page picks by the calendar the reader
  keeps, `targum:schedule`, the diaspora's until they say, as `/parasha` defaults. A
  Diaspora / Israel switch is drawn only in a week the two read different portions, and
  a press is kept; Learn's `/series` and the bell now ask by the same calendar.
- Portions open in the Library (targum-internal#410). A portion's row, among the cards
  and in the table, is a link to its reader, which the box builds once for everybody, so
  opening one builds nothing and spends nothing. A signed-in reader opening
  `/library/parasha-<slug>` or `/open/parasha-<slug>` is sent to the same reader, with a
  302 because the answer depends on who asks; a stranger still gets the 301 to
  `/parasha/<slug>`, which stays the public page. The reader answers a signed-in reader
  even where the shelves are shut to strangers. Learn's door names the reader through
  the same helper (`parasha.build.reader_href`), and the bell opens a followed series'
  reader rather than its public page, as Learn's door already did.
- "Life in Israel", a subject of its own (targum-internal#393): `Tag.israel` and the
  arrival's `israel` door, said "Life in Israel: money, health, school, home" and in
  Russian, and a Library chip. One subject for the four olim ones of #386, by decision
  (2026-10-02). The `everyday` door, which files the dialogues by form, is now said
  "Everyday conversation" so that it does not read as the same thing.
  `scripts/file_life_in_israel.py` writes the missing catalogue rows for scenes 101–200,
  which were on the shelf but not in the Library, and tags the 48 olim clips. It is a
  dry run unless given `--write`.
- The corpus ledger, designed and started (targum-internal#162). `LEDGER.md` is the
  design: one SQLite file, a table per artefact kind, every row naming the tool and the
  version that made it, the cache becoming a view of it a stage at a time, rebuild from
  rows, `targum corpus export --exportable`, the migration and the open questions. The
  first slice is `src/targum/ledger.py`, for the `vocalize` stage only and **off unless
  `TARGUM_LEDGER` names a file**. With it on, `Cache.put` writes its JSON as before and
  then the same pointing as rows (`vocalizations`, `pointings`), and `Cache.drop` drops
  the row too. A value is kept only if the rows give it back byte for byte. Nothing reads
  the ledger yet: the cache is still the read path. `ledger.rebuild` writes the cache
  back from rows and `ledger.backfill` reads today's cache in; against this laptop's
  cache that recorded 936 pointings and refused none.
- The Hebrew stress rule fed by a local tagger instead of OSHB (targum-internal#325).
  `scripts/eval_stress_tagger.py` scores `stress-rule/1` on the same 3,000 held-out words
  of `tanakh-taamim-v2` with two $0 taggers. DICTA's own morphology (`dictabert-joint`,
  the Hebrew annotator, run over each verse unpointed) gives 0.9377, or 0.9393 with a
  perfect behind a vav read as vav-consecutive; it misses the possessive suffixes the
  Bible writes on the noun and the directional he, which it does not tag. A logistic
  tagger over the pointed word's letters and vowels, trained on words 3,001 to 23,000,
  gives 0.9510, and 0.9520 reading DICTA's tags as well. Against 0.9137 from the pointing
  alone and 0.9630 with OSHB. There is no modern Hebrew stress gold to score either on.
  Nothing shipped reads any of it: `phonikud/2` and `SCHEMA_VERSION` are unchanged.
- The Hebrew stress eval measures the pause and a grammar rule, both free
  (targum-internal#325). `scripts/eval_hebrew_stress.py --baseline-only` now also writes
  the share of the gold under a pausal accent, read by `vocalize/trope.py` (10.4% under
  etnachta; 24.4% with segol, shalshelet and zakef), each accuracy without those words,
  and `stress-rule/1`, a binyan and mishkal rule — segolates, the dual, furtive patah,
  the suffixes and perfect endings that keep the stress back — scored on the 3,000 words
  it was not written against. Pause barely moves the default (0.7630, 0.7649 without
  etnachta). The rule takes it to 0.9630 with OSHB's tagging and 0.9137 from the pointing
  alone. Nothing shipped reads the rule: `phonikud/2` and `SCHEMA_VERSION` are unchanged.
- `/how`, how targum reads Hebrew (targum-internal#401): the hard parts of Hebrew for a
  machine, each shown solved on a real text. Vowels put back on the weekly's news with the
  reader's switch, one spelling read as two different words, prefixes taken off down to the
  dictionary form, one root across three patterns from Genesis to the news, a recording's
  sentences and word times, a reel and a chat in their own shapes, and Onkelos with its own
  word list. Every example is copied out of a build by `scripts/how_examples.py` into
  `src/targum/how.json`, which the page draws; the script refuses a pick that has moved.
  Credits for DICTA, Open Scriptures, the Metsudah Chumash and the reel's author. Linked
  from the foot on every page and from /about, open to strangers, in robots and the
  sitemap, and in Russian.
- A rail that can only say no now stands in front of `record_turn`'s claim, the one
  spend a model decides (targum-internal#324). `chat/rail.py` refuses, before anything is
  claimed or a model asked, a line carrying the contract's "> ", "= " or "~ " marks, an
  arrow or a "Corrected:" label; a link, a code fence, HTML, JSON, a snake_case name or a
  site's menu; fewer than a third of its words in the language's own script; one stray
  Hebrew letter; one word making most of a long line; and a French, Italian, Spanish,
  German or Ukrainian line tagged as another language, by wordfreq. A fault in it is a
  no. On the 86 labelled arguments it takes the checks from 15 of the 59 that should not
  spend to 36, with no false block on the 27 that should, nor on 32 more of a reader's
  own lines written after it; `scripts/eval_rail.py` now prints both rows. Jev is not
  measured here.
- The week's shnayim mikra sheet as a PDF: `targum export mikra` (targum-internal#105).
  This Shabbat's portion — or the week of `--on` — with Onkelos beside each verse, the
  haftarah the calendar names for it with the reader's language beside it, and with
  `--for` the words that account looked up that week, with the meanings it kept beside
  them — or, where the record names no look-up, the words it kept, and the heading says
  which. A look-up in the record of use now names its word (a new `event.word`, schema
  39), still behind `TARGUM_EVENTS` and the reader's switch; the privacy notice (clause
  3.6, amended 28 September 2026) and the account page say so. Cut from the books on the
  shelf as the portion page is, so it costs nothing; the same `print` extra. design.md §12
  (2026-09-28) says what the sheet adds.
- `targum video discover`: finds Creative Commons videos to curate through YouTube's Data
  API and prices building them, for approval before anything is bought
  (targum-internal#382).
  - It searches each of he, ru, it and fr by everyday topics in the language's own words,
    short videos first.
  - It asks `videos.list` for each hit's licence again and keeps only `creativeCommon`
    that is public, embeddable, 30 seconds to 20 minutes long, credits a channel, and is
    not labelled as another language.
  - It skips what is already on the curated shelf.
  - It prints the batch as a markdown table with a tick box per row and an estimated
    cost, using the pipeline's own before-hearing arithmetic. It writes the candidates
    to `targum-out/discover/`.
  - Data API quota is budgeted per run (`--quota`, 2,000 units by default of the day's
    10,000) and reported.
  - Nothing is fetched, built or spent. The key is `TARGUM_YOUTUBE_API_KEY`.
- `/about` says what was built, day by day. Under the calendar, every day since the
  first has one to three plain lines, newest first, from `src/targum/built.txt`. The
  heading is "targum is built in public". The lines are English on every page, and the
  Russian page says its own heading and dates around them. Nobody reads a day's lines
  before they are shown, so `about.refused()` does: it holds each line to design.md §6
  and refuses the workings, the back office and where a text comes from. It is asked by
  `tests/test_about.py` over the file and by the page over every line it draws.
  `deploy/built.md` is the brief the lines are written to. The count's last day is said
  in the page's language, where the Russian page said "по 29 September".
- `targum levels`, the level map (targum-internal#382): every catalogue text placed on the
  weekly's Easy, Simplified and Native by both halves the weekly checks its own editions
  against — hard-word share and words per sentence — per language, split into text, audio
  and video, with the texts meeting the Easy spec in full (both bands, three minutes or
  less) counted against a target of 100 each in he, ru, it and fr. Reads the catalogue and
  the disk; fetches nothing and spends nothing. Catalogue rows carry `sentence` beside
  `difficulty`: `scripts/measure_difficulty.py` prints it, `promote.accept` writes it, and
  until a sweep has, the map reads it off a build's `segments.json` or segments a curated
  video's document on the spot. The weekly's gauge counts sentences by the same
  `annotate.difficulty.sentence_length`.
- Test accounts, wiped at every sign-out: `targum test-account EMAIL` marks and invites
  an address, and signing out of it empties everything it holds while keeping the account,
  so the next sign-in is a new reader's first visit. Refused for an address that already
  has a real account; `--link` prints a one-time sign-in link for a test account only.
  deploy/README.md, "A test account".
- `targum eval <stage>`, one command for any stage's eval (targum-internal#351). A thin
  dispatch over the harnesses in `scripts/`, which stay where they are; everything after
  the stage goes to the script. `lemma` and `stress` are each measured two ways, so they
  are named by corpus: `lemma/iahlt`, `lemma/ud`, `stress/tanakh-taamim`,
  `stress/wiktionary-ru`.
- The first Hebrew lemma rows in the ledger, from a human-tagged source: the shelf's
  DICTA annotator against the IAHLT dev split, lemma 0.8244 on `iahltwiki` and 0.7836 on
  `iahltknesset`, part of speech 0.9789 and 0.9745 (targum-internal#351). With floors
  a little under each.
- The shelf-search questions, asked of Jev (targum-internal#319). `shelf_screen.py` asks
  what every research run asked of every candidate — in the language it claims, original
  or translation, which subject, prose or not, would a learner get through it — over what
  a candidate says before anybody takes it, and reads the licence line in code, never
  through the model. `scripts/screen_shelf.py` sweeps the catalogue with it and scores
  each answer against what the owner wrote on the rows they kept. Over all 967 rows, for
  $0.044: language 0.996, prose 0.997, origin 0.932 (0.991 once fifteen rows whose notes
  answer a different question are set aside), subject 0.708, recall on accept 0.996.
  Precision cannot be measured: the rejected half of the research runs was deleted on
  2026-09-27, so the set holds no reject.
- `scripts/eval_rail.py` measures whether a rail that can only say no, in front of
  `record_turn`, would stop anything the tool's own checks let through
  (targum-internal#324). It scores 86 hand-labelled arguments. The checks alone stop 15 of
  the 59 that should not spend, and wrongly stop none of the 27 that should. With a Jev
  "no" in front, at a refusal weight of 0.7 or more, 48 are stopped, still with no false
  blocks. Nothing is wired in; this is the measurement the card asked for first.
- The scene gate checks numbers and construct chains (targum-internal#134):
  `dialogue/agreement.py` reads DICTA's morphology and syntax for a numeral in the wrong
  gender or state for what it counts (שְׁמוֹנָה יְחִידוֹת, בִּשְׁלוֹשָׁה הַחוֹדָשִׁים) and for a
  construct chain the points break (לָרוֹב הַדִּירוֹת, a verb pointed as הַפְרָעַת).
  `scripts/score_scene_checks.py --dicta` scores each against the 384 settled corrections:
  7 of the 9 number errors and 11 of the 18 construct errors, in 25 findings of which 22
  are settled corrections and the other 3 read as real errors the settled set lacks. The
  free gate goes from 10 settled errors to 32.
- A second wording for how hard a sentence is, `without-register`, which takes "literary",
  "classical", "archaic", "poetic" and "rabbinic" off the top three rungs, and
  `scripts/sentence_bias.py`, which asks it and the library's wording of 200 verses and
  200 lines of modern prose matched on the share of their words a reader at gimel knows,
  and on length (targum-internal#320). Switchable with `--prompt`; the library's wording
  stays the default, and the compiled file now says which wording it holds.
- Who says a line, measured before anything is voiced (targum-internal#77):
  `scripts/measure_speakers.py` takes the catalogue's Hebrew plays as free gold, strips
  the names, asks Sonnet who says each line and how sure it is, and prints accuracy and
  a precision–coverage curve over the confidence (`targum/speakers.py`). A play's turns
  are explicit and alternate, so the number is an upper bound for prose. Nothing is
  voiced and the reader is untouched.
- The words to know before a chapter, behind `TARGUM_PREREAD` and off
  (targum-internal#97). A folded list above a chapter's first line: its hard words by the
  printed edition's rule, the commonest first with how often each comes round, forty at
  a time, each with its first sense. The page carries more than it shows, and a word the
  reader has marked known or put aside comes off as the page opens, in the browser, with
  nothing asked of the server. Decided when a reader is written: with the switch unset a
  page is byte for byte what it was. design.md §12 (2026-09-28).
- A French word read into English can name its false friend: *actuellement* adds "false
  friend: not *actually* — currently" to the card (targum-internal#267), **behind
  `TARGUM_FALSE_FRIENDS`, off until the list is reviewed**. Decided when a reader is
  written; unset, a reader is byte for byte what it was. The 315 entries are targum's own
  list, `annotate/false_friends.json`, drafted and checked by Claude Opus 5 with
  `scripts/false_friends.py` and checked against Grammalecte's lexicon for the lemma. **No
  person has reviewed it yet**, and the table says `"reviewed": false` until one has.
  LICENSING.md says how it was made and why nothing was copied.
- How a French word is said, behind `TARGUM_FRENCH_IPA` and off (targum-internal#266). The
  word card gives the word's IPA as it is said in its sentence, from Morphalou alone, and
  a French reader's `n` is the "as said" switch: a tie and its consonant over the
  liaisons every speaker makes (a determiner before its noun, a clitic before its verb, a
  verb before its inverted pronoun, with gruut's consonants), the elisions, and the final
  consonants nobody says in muted ink. Drawn by a stylesheet over characters already in
  the text, so no offset moves and a word saved with it on is the word saved with it off.
  Optional liaisons are left unmarked. A word Morphalou has no reading for shows none; a
  hyphenated compound is said by its parts. `un` never takes `une`'s reading, and `c'` is
  /s/ by a one-row correction published under LGPL-LR
  (`annotate/morphalou_corrections.tsv`). Against a model-drafted gold of 342 sentences
  from four public-domain texts on the shelf, not yet read by a person
  (`evals/french-said-gold.jsonl`, `scripts/eval_liaison.py`): liaison precision 1.0 (80 of
  80, floor 0.98), recall 0.71, IPA word accuracy 0.9998, coverage 0.976, all with the
  gold's own tags. Decided when a reader is written: with the switch unset a page is byte
  for byte what it was. design.md §12 (2026-09-28).
- Morphalou 3.1, the ATILF's open lexicon of French, as a fetchable lookup:
  `targum models fetch morphalou` downloads it from ORTOLANG, checks a pinned sha256 and
  keeps it in the model directory, never in the repository (targum-internal#266). LGPL-LR,
  whose text is now at the end of `LICENSING.md`. Nothing reads it yet. The first step of
  the French pronunciation card was to count how much of the shelf it reaches, and
  `scripts/measure_pronunciation.py` does: 97.9% of the French shelf's word tokens and
  96.1% of its types on 2026-09-28, every text above 95%, with the misses mostly names,
  `M.` and hyphenated compounds.
- The chanted Torah keeps a clock for every word (targum-internal#329). `parasha
  leyning` used to collapse the aligner's word timings to one span per verse before it
  stored them; the manifest now keeps them, as `clocks` on each part, verse ref to one
  [start, end] per word, and still writes the verse spans, read off the words, so
  nothing that asks for a verse changes. A reader built from a re-attached portion gets
  the same word rows prose already has, so the card's ear and the player's word-by-word
  step work on the Torah too. A trope phrase's span is read off the same clocks at build
  time (`Part.phrase_spans`), for "hear the phrase" later; nothing draws it yet. A
  manifest attached before today has no `clocks` and reads exactly as it did. Getting
  them is `targum parasha leyning --again`, and costs no alignment where the old one is
  still cached: Bereshit came back in about a second with the same verse spans. Where it
  is not, about a minute an aliyah.
- A word of scripture names its accent on its card (targum-internal#329): one muted line
  under the reading, "tipcha · disjunctive", while the chanting marks are shown. The
  accent is the one that rules the word, read by `vocalize/trope.py` at build time;
  meteg is never named, and Psalms, Proverbs and Job get no line, their accents being
  another system. In Russian the name is transliterated and the class translated
  («типха · разделительный»). design.md §12, "A word in scripture names its accent".
- A French object pronoun says what it is to its verb, and a French verb says the
  imparfait and the passé simple (targum-internal#264, with #263's two deferred lines).
  An object *le* read "he" and *en* and *y* read nothing; now *la* reads "direct object ·
  f", *leur* "indirect object · pl.", *en* "of it / some", *y* "there / to it" and *se*
  "reflexive". *Mangeait* reads "imperfect · he/she", *mangea* "simple past · literary",
  and *eut mangé* the past anterior beside *avait mangé*'s pluperfect.

  One grammar question for all of it, prompt 3 (`model_lemma.PROMPT_VERSION`): `Tense`
  takes `Imp`, a French clitic takes a `Role`, and a sixth column copies the words it
  stands for from its own segment or the one before. Scored on GSD dev: French tense
  0.8933 → **0.9831**, Italian 0.7545 → **0.971**, French role 0.9286 over 28 clitics, with
  floors. The words a pronoun stands for are read and kept but not shown: the card names
  them only at a measured precision of 0.9 (`ANTECEDENT_PRECISION`), and the hand-written
  set that measures it waits for a person. The page and its "stands for" button are built
  behind that gate.

  **Nothing on the shelf is read again by this.** A lemmatizer that is not buying a
  segment takes its prompt-2 reading rather than dropping the words, and says so in its
  name (`/with-2`), so a deploy's `rebuild --words` keeps every French, Italian and
  Yiddish text as it reads now and the page keeps calling a finite past "past".
  `targum rebuild --reread fr` is the paid re-read, and `--dry-run` says what it costs
  first; it reads again only the segments a text already had words for.
- The Tanakh map, `/tanakh-map` (targum-internal#144): every chapter of the Tanakh a
  square, in the Torah, the Prophets and the Writings, grouped by book in the Hebrew
  order and count, and shaded on the knowledge ramp by the share of its running words
  the reader has marked known — `coverage.chapter_map` from #490, asked once a visit
  through `/tanakh-map.json`. Every square links to where its chapter is read
  (`/open/<book>#<chapter>:1`), so the map is also a table of contents; hover or focus
  shows the chapter's card, and on a phone a tap shows it and the card's Read is the
  press. The Aramaic chapters are marked as Aramaic and never shaded as Hebrew, a book
  the library lacks is drawn as unavailable, and this week's portion is ringed in ink.
  Reached from Your Progress under Hebrew. design.md §12 (2026-09-28) records the ramp's
  turns and the Aramaic treatment. The public test (`/tanakh-hebrew-test`) is not here.
- A reader's edition as a PDF: `targum export pdf <folder>` (targum-internal#105). The
  text with its vowels, and its te'amim where it is scripture; the translation beside
  each line as the parallel mode sets it, or under it with `--under`; and after each
  chapter the words worth having on the page, with their first sense — the hard words,
  or with `--for` the ones an account has not marked known. Set from the folder alone,
  in the reader's own carried Hebrew face, by WeasyPrint through Pango and HarfBuzz so
  the marks sit where a browser would put them. An extra, `print`, because it needs
  Pango on the machine; design.md §12 (2026-09-27) says what paper keeps of the reader.
- targum in Claude and ChatGPT: the connector, with a token that names a person
  (targum-internal#80). A reader adds targum by pasting one address and pressing Connect,
  and the tools they already had in the chat answer about their own shelf, their own
  ledger and the library — from wherever they already ask. `/connect` says how, assuming
  it is their first connector of any kind: one block per host, each with its own steps,
  and nothing detected or guessed.

  It is OAuth 2.1, because both connector directories require the flow and because a key
  pasted into somebody else's client is a bearer credential with no scopes and no way to
  take it back one client at a time. Authorization code with PKCE (S256 only), dynamic
  client registration, the two metadata documents a client reads off a 401, and refresh
  tokens that rotate — so a refresh token presented twice finds itself revoked, which is
  the one signal available that it was copied. Nothing is stored in the clear: codes and
  tokens are digests, as sign-in links and sessions already were.

  Three scopes, and the reader grants them on a page of ours. The library and what is at
  a link; their words, their mistakes and how far they have got; and checking their
  Hebrew and pricing a text, which is the one that uses their hours and says so before it
  is granted. What each connector holds is listed on the account page and taken back
  there, both kinds of token at once.

  **One standing rule changed, and design.md §12 records it.** A chat tool could not
  spend at all; now exactly one scope may say otherwise, because the record only fills if
  something recasts what the reader wrote. Everything else holds: a build still needs its
  own press, and a quote made through a connector comes back carrying a link to the page
  the button is on rather than a way to spend. The model never presses anything.

  The transport is JSON-RPC over the server targum already runs — no second process, no
  SDK on the box, and no session held between two calls, so a deploy can restart
  mid-conversation without a client noticing. `Mcp-Session-Id` is deliberately absent.
  Prompts are offered by name — what to read next, work on what you got wrong, read with
  me — which is how a reader reaches targum without having to describe what they want.

  And Learn's row of doors takes a third that is not a text, styled exactly like the two
  that carry one, because a door drawn as a lesser thing reads as an advertisement on a
  page that promises to pull and never push.
- The privacy notice says what the record of use is. Two clauses under the categories of
  data: the reader's own record, kept to show them their time and words, which they can
  stop or erase from their account page; and counts across everybody that carry nobody's
  identifier and leave uploads out. A line in the retention schedule, the record named
  in what closing an account deletes, and clause 3.10 no longer says nothing of what a
  reader does is kept. This is what `TARGUM_EVENTS` was waiting for
  (targum-internal#127).
- Two more first-run moments, each a line said once and in place. When a new reader marks
  their first word on a text that has a recording, the line under the bar says "Now press
  play. The page follows the voice, line by line", and the press puts it away. The first
  time What to work on has anything in it, it says whose words they are and that they
  will be waiting. And the text the arrival opens is one that can be heard, where the
  reader's subject has one. Nothing opens on its own, nothing moves the page, and nothing
  is counted (design.md §12, targum-internal#335).
- Where a word comes round, on its card. Behind `TARGUM_OCCURRENCES`, off unless the
  deployment sets it; off, the card is the card it was and asks nothing. On, the card
  asks `GET /word/met` once when it opens and says how often the word comes round in
  this text and in the Tanakh ("4× in this text · 241× in the Tanakh"), where the reader
  met it ("met in Jonah 1:4, Ruth 2:1 and 6 more": a verse by its reference, any other
  text by its title, latest first, three named), and for a verb how many words of its
  root they have met and know ("6 words from כ־ת־ב met, 3 known"). The root becomes the
  way in to those words. "Met" is the index's: inside a section the reader finished,
  never the page they are on. The index now keeps each form's root, so its cache is
  counted again on first ask, which reads the annotation and spends nothing
  (design.md §12, targum-internal#95, #96).
- A record of what happens in a text, and Time and words on Your Progress. Behind
  `TARGUM_EVENTS`, off unless the deployment sets it: a word looked up, a stretch of a
  recording played, a page turned, a section finished, where a sitting stopped and which
  of the reader's controls was pressed are appended to the account (`POST /events`) and
  never merged or sent back. Your Progress reads time listened, time watched and words
  read off it (`GET /account/totals`), with filters for what the reader was doing and
  when; the panel is absent where there is no record. A word is read when its page was
  turned past or its section marked done. The account page says what is recorded and has
  a switch that stops it and an erase that asks twice. A control pressed carries its
  name, the window's width and the day, and the server drops anything more
  (design.md §12, targum-internal#127, #339, #341).
- The arrival asks one question a screen, and leads into a text. A new reader is asked
  what they are interested in, then how much Hebrew they have, each on its own screen with
  a Skip, and the last answer opens the text it chose instead of returning to Learn. On a
  phone the arrival is the screen: the nineteen subjects wrap as pills where they stood as
  nineteen rows, and Next and Skip stay at the foot of the window. The level is said as
  what a person can follow ("I follow the news, with a dictionary"), and it is kept on the
  account as a seed: it chooses how hard the first text is, which band the Library opens
  on and how hard the conversation writes, until the reader's own marked words reach a
  rung, and from then on it is not read. It is never shown back. Learn on a phone leads
  with one card that carries the page's one filled button (design.md §12,
  targum-internal#334, #306).
- What to work on turns over. The fold showed the same rows on every visit, because it
  is ordered oldest first and a word's stamp is written once. The order stays. Each visit
  now opens where the last one ended, a press at the foot ("Show others") turns to the
  next screenful, and off the end it comes round to the oldest again, in both tabs and on
  both pages. The place is kept by the row and not by a position, so marking a word does
  not move the rest, and it is kept in the browser only. The press is drawn only where
  there is another screenful, and says nothing about how much is behind it
  (targum-internal#336).
- The Beit Midrash: a third tab on the Library, for Hebrew, that walks the Tanakh and the
  Judaica as a tree the way Sefaria's contents does. It opens on its doors — Tanakh, the
  Torah by portion, the Aramaic translations, Mishnah, Halakhah, Thought and ethics, Liturgy — each saying
  how many texts stand behind it, and behind a door every shelf stands open under its own
  heading, so the tab, Tanakh and Ruth is two presses. It is not the second room the old
  Beit Midrash shelf was: every text in it is also under All texts at the same address,
  drawn by the same rows and cards. The level band does not apply there, the search looks
  behind every door at once, and the tree has an address (`#bm/tanakh`). The Targums have
  a door and stay Aramaic: they open as Aramaic readers and their words go to the Aramaic
  list. Which door a collection stands behind is a field in the catalogue file
  (`Collection.door`), and a file that says nothing draws no tab (design.md §12,
  targum-internal#340).
- A Russian page can show every word in one case. A "cases" choice in the bar lists the
  six cases with how many words of each the page has ("genitive · 12"). Choosing one gives
  those words the highlight wash and a dotted underline, `c` steps to the next case, and
  Escape clears it. It is off until asked for, shows one case at a time, and is not
  remembered: always-on grammar colouring costs comprehension (Lee & Huang 2008), and
  design.md §4 allows one functional hue at a time and never colour alone. Pages whose
  words carry no case, which is every page outside Russian and Yiddish, have no such
  control (targum-internal#261).
- Russian stress marks. A Russian reader's `n` switch shows an acute over the stressed
  vowel and restores ё. A word is marked only where silero-stress (MIT, the new `stress`
  extra, which the deploy installs) and OpenRussian's tables agree on one stress. A
  homograph is settled only by the case and number the tagger gave it, so the stage runs
  after the words. Names, one-vowel words and the first half of a hyphenated word are
  never marked. On 1,000 sentences a person stressed by hand in Wiktionary the marks
  placed are right 99.8% of the time, and 83% of the words that need a mark get one
  (`scripts/eval_stress.py`, floors in `evals/floors.json`). The marks are combining
  characters after a Cyrillic letter, U+0301 and U+0308, so every offset, saved word
  and phrase is the same with the switch on or off; the same code points after a Latin
  letter stay text. `rebuild --words` marks a Russian text already on the shelf, and
  marks it again when its words are read again (targum-internal#260).
- A Russian verb's card names its other aspect, stressed ("the other aspect: говори́ть").
  Where the partner is used in the same text, the card offers to go and read it there.
  A word whose stress moves across its forms says where: "stress moves: рука́ · ру́ку".
  Both are looked up in OpenRussian.org's dictionary tables, CC BY-SA 4.0, which
  `targum models fetch openrussian` puts in the model directory and the deploy fetches.
  They are never committed, packaged or trained on, and a page that used them credits
  them at its foot. A spelling the dictionary files as two words gets neither line. Asked
  about a verb's aspect from its card, the chat is pointed at a new tool,
  `sentences_with`, which finds sentences using a word in any of its forms across the
  reader's shelf, so it can set the partner's sentence beside this one
  (targum-internal#259).
- A Russian word's card names its case and its aspect: "noun · f · accusative", "past ·
  perfective · m", "future · perfective · he/she", "past participle · perfective · f ·
  genitive". The model that reads French, Russian, Italian and Yiddish words now writes
  each word's grammar in the same pass, a fifth column of Universal Dependencies features
  from a fixed list (`model_lemma.FEATURES`), and the case and aspect are scored against
  the SynTagRus dev set beside the dictionary forms, with floors (`scripts/eval_lemma.py`).
  The card also lists the other forms the word takes in the same text ("here also as рука
  · рукой"), and a question asked from the card carries its grammar line, so the answer
  explains the tag the reader saw and says so when the tag is wrong. Hebrew cards are
  unchanged. The question is prompt 2, so every French, Russian, Italian and Yiddish text
  is read again, and paid for again, on its next build (targum-internal#258; the research
  is `research/russian-cases-aspect-stress-2026-09-14.md` in targum-internal).
- The Aramaic shelf has Aramaic texts of its own. Sefaria's public-domain targums can be
  fetched by the title Sefaria files each under — Targum Jonathan on the Torah and on the
  Prophets, the targums to the Writings and to Chronicles — pinned to one surveyed edition
  apiece, the licence still asserted at every fetch (`sefaria.TARGUMS`). An English is
  paired with one only where a complete one may be served: Etheridge's Pseudo-Jonathan,
  the 1871 Isaiah and the Community Translation of Jonah (`sefaria.TARGUM_ENGLISH`).
  Every other English on offer was measured and is mostly holes. A Torah book carrying
  Onkelos as a column is no longer filed under Aramaic, which had made the Aramaic shelf
  the Hebrew Torah.
- French, Russian and Italian can be read, beside Yiddish, with a word card on every
  word. No Stanza model for any of them clears the licence bar, so their dictionary forms
  and parts of speech are read by the model (`annotate/model_lemma.py`, Haiku 4.5): a
  sentence at a time, cached forever by its text, scored against each language's Universal
  Dependencies dev set before it is trusted (`scripts/eval_lemma.py`, with floors). It
  costs money where Stanza did not, so it keeps targum's rule: the card's price includes
  reading the words, only a build that was pressed may buy them, and a book's words are
  read with the chapters bought, the later ones merged in as they are. Everything that
  prices, repairs or rebuilds reads from the cache alone. Hebrew's annotator and its name
  are untouched. A text whose language nobody chose and whose guess lands on one targum
  does not read — Latin script guesses English — is asked for its language instead of
  being built; Yiddish is told from Hebrew by its ligatures and function words; and a
  French, Russian or Italian reader no longer carries the Hebrew typeface. The quote
  rates for the four languages were measured with the counting endpoint, and
  `LICENSING.md` records the dev sets as evaluation-only and says precisely what wordfreq's
  CC BY-SA tables reach.
- Read-aloud in French, Russian and Italian. The voice was told "Read this Hebrew aloud"
  whatever the text was; it is now told the text's language (`speech.ask`), Hebrew's
  instruction byte for byte as it was. "Hear this section" is offered on a silent section
  in any of the four, and a spoken reply is read in its conversation's language. Yiddish
  and Aramaic are not offered a voice and are refused at the door: Gemini's speech model
  lists neither, and a Hebrew reading of their letters would be wrong.
- French, Russian and Italian show a CEFR level on Your Progress, and Hebrew's ulpan rung
  shows its CEFR equivalent beside it ("aleph · about A1"). The CEFR is climbed by known
  words among the language's commonest five thousand or so — read off the band every
  marked word already carries — with levels from Milton and Alexiou's measured vocabularies
  for learners of French (A1 250, A2 1,350, B1 2,000, B2 2,400, C1 2,750, C2 3,300),
  borrowed for Russian and Italian. The distance is in words ("Another 100 common words to
  B1."), the page still says "A guide, not a placement.", and Yiddish and Aramaic keep
  their milestones with a line saying why. The chat is told the reader's ladder in their
  language and still never tells them their level. `level.py` and `charts.js` carry one
  ladder per language, pinned to each other by the node test; `design.md` §12 records the
  decision.
- A language menu at the end of the nav on every desk page — Learn, Library, Your
  Progress, Add and the conversation — replacing the row of tabs only three pages drew
  (design.md §13). It lists every language the reader learns, says which the page is in,
  and ends with "Your languages". A press is kept on the account (`POST
  /account/language`, `current` in the `chosen` table, no migration), so another device
  opens in it; opening a text never moves it. What follows it: the Library and Learn's
  shelf; Suggested (`/suggest?language=`); a file brought into the conversation, filed in
  that language; and the conversation itself, one per language — Hebrew's exactly as it
  was, any other language in the English find mode until it has a conversation of its
  own. The Add page's language picker and the menu move together, so switching never
  loses what is in the box. "Which Hebrew" and the followed series hide under another
  language. A text written in two languages — Daniel's Hebrew and Aramaic — is on both
  shelves (`/readers` gives `languages`), and a word marked in an Aramaic row is kept in
  Aramaic's list rather than Hebrew's, while a word Hebrew's list already held stays put.
  The drawer in a reader opens the conversation of the line's own language.

### Changed
- The front door's English says what the app does now (targum-internal#477, from
  ling-en's pass). "How you learn" no longer promises the ulpan ladder, which Your
  Progress dropped: the card says Your Progress shows the kinds of text you can follow,
  and its demo reads "2,140 words known · You'd follow most of a news article", the
  page's own sentence. The library heading counts what the live Library links, more
  than 700 Hebrew texts and videos (720 on 2026-10-21), where it said nearly 500, and
  `/connect` says the same. "Cantillation marks" replaces the in-house "chanting marks"
  on this page, the Aramaic chapters keep "a word list of their own", the phone's link
  says "Save as a text" as the chat's button does, and four answers lose their colon
  lists and passives. The cost answer names no price and promises no early word of one;
  the tap card still says each vowel we add is marked (design.md, 2026-10-02). The expired sign-in link's heading is "That link no longer
  works", since it may have been used rather than timed out. The link preview's alt is
  a string key (`public.head.preview-alt`), so the Russian page can carry its own.
  The Russian lines were redrafted and re-stamped with it.
- The front door's lede is two plain sentences and an offer: "Everything here arrives
  ready to read. Every word has its vowels (nikkud) and every line has its English
  beside it. Tap any word and we'll explain it." It opened on an aphorism and carried a
  colon list. The headline and the four points under the box are unchanged, as design.md
  holds them (2026-10-02, amended here).
- design.md §12 "Every text has a picture" now says what happened: the image-model batch
  David approved on 2026-10-08 drew 735 library covers, and the 152 rows it missed (151
  filed after it, one it skipped) were drawn on 2026-10-21 (targum-internal#429). The
  section now lists four places a picture comes from, in order: the text's own, the
  library's licensed batch, a drawn cover, and the letter tile until a cover is drawn.
  Before this it said the batch "is not done".
- A video text has a viewer of its own (targum-internal#422, David's A + B + C from the
  mockups). **Beside**: the picture at the left with one thin row under it — play and
  pause, the time, a hairline of where the voice is (the line being said a faint band on
  it), the length, the speed ("1× ▾", the six speeds as one of the bar's panels) and Loop
  this line — then the title, the source, the licence, the part and "Watch on YouTube",
  and the transcript beside it following the voice, the line being said lit as a chanted
  verse is, English under each line, and the word being said lit where the recording was
  aligned word by word. **Theatre**: the picture large and, under its row, the line being
  said set large — the transcript's own words, tappable with their levels, the spoken
  word lit — its English small under it and the lines either side faded; Transcript
  opens the transcript as a panel and the picture grows smaller. The bar carries a
  **Beside | Theatre** switch, kept per reader (`targum:film-view`), and `v` turns between
  them; Listen stands down while the picture is up. **C**: while it plays, the bar and
  the row step back to the picture, the hairline and the line; a pause, the pointer, a
  touch or a key brings them back, and nothing steps back while a panel or a word's card
  is out. A word tapped while it plays stops it: the card opens over the paused frame,
  which steps down under it, and the word stays marked in the line. ↑ ↓ step a line
  (← → too in Theatre with the transcript put away). On a phone: the picture the window's
  width, its row under it, and the transcript under that. It replaces the picture in a
  corner (picked up, moved and sized), its own full-screen mode and the floating strip
  that stood under it: full screen is the browser's, under ⋯, as on every text; ⋯ also
  carries the picture on and off, Hear first, the step either side and the file while
  the picture is up. Put away, the page is an audio reader, with Listen and the strip,
  whose toggle brings the picture back; that is still kept per text. The stores of the
  corner, the place, the size and full screen are no longer read. Inside a playlist a
  video opens in Theatre, writing nothing, and its end opens the transcript. 25 Russian
  strings are new (see the PR). design.md §12 has the entry; the tests that pinned the
  corner, the drag, the size and full screen went with them
  (`tests/test_video_viewer_browser.py` has the new ones).
- The reader's bar is one calm row on every text (targum-internal#421, David's A + B + C
  from the mockups): the mark, the title, "N of M known", and at the far end Listen (the
  recording choice inside it, "Chanted ▾", where an aliyah has two), Aa, print (on a
  portion's reader only) and ⋯. Nothing was taken away. **Aa** holds the translation, the
  columns beside the verse (Translation, Onkelos, Rashi, Rashi · English, only those the
  text has), shnayim mikra, the vowels or stress marks,
  the te'amim, "As said", text size and line spacing, as plain rows with quiet switches.
  **Print** is a two-line choice, this aliyah or the whole portion and its haftarah. **⋯**
  holds the view (beside, under, the text alone), pages or one scroll, highlighting, the
  word list, the case lens, the picture and the original, full screen, talk, keys, Add to
  playlist and Hear this section. No filled dark pills: the live choice is underlined in
  leaf. The columns switch themselves: a quiet × on a column's name under the pointer
  hides it, and a hidden column waits as a faint "+ Rashi · English" at the head of the
  first verse. The bar steps back while a reader scrolls on or listens, to the mark, the
  count and pause with a thin line of where the voice is; it comes back for the pointer
  at the top, a scroll up, a pause, Escape or keyboard focus in it, never steps back
  while a panel is out, and stays solid paper (it was frosted glass) at one height. Every
  panel is a dialog or group with `aria-expanded` on its press, takes focus when opened
  from the keyboard, gives it back on Escape, and shuts on a press outside; on a phone
  each is a sheet from the foot, and the × is not drawn. Read is the only layout:
  shnayim mikra is its own switch in Aa ("Each verse twice in Hebrew, then once in
  Onkelos"), offering By verse and By aliyah while on; meanwhile the column switches
  are grey with "Shown in Read", and pressing one puts the practice down and brings that
  column back. The player strip no longer stands at the foot when a recorded text opens
  (reversing design.md §12, 2026-09-03): ▶ Listen starts the voice and brings up a slim
  strip with the line, step, speed, Hear first, the file and ×; × puts it away and
  returns focus to Listen, and nothing is remembered. A text with video keeps its strip,
  which is the picture's transport. `TargumPlayer.show()` brings it up without playing.
  Ten new strings, in Russian too.

- How hard a sentence is is now asked, by default, in the `without-register` wording, whose
  top three rungs say how rare a word is and no longer call it literary, classical,
  archaic, poetic or rabbinic (targum-internal#320, decided 2026-10-03). The library's
  sentence levels were scored again in it. The old wording stays askable as
  `--prompt situations`, and answers that do not name a wording are still read as it.
- The Hebrew annotator keeps DICTA's syntax (targum-internal#134). Each word now records
  which word governs it and how, with its prefixes (`Token.syntax`), and the first word of
  a construct chain says "construct" on its card: בֵּית in בֵּית הַסֵּפֶר. Until now no
  card ever said it, because DICTA's morphology never marks the construct and the
  annotator threw away the syntax that does. The scene gate's smichut and numeral checks
  read the stored annotation where it carries the syntax, and read the scene again with
  local DICTA where it does not (`dialogue/agreement.py`, and
  `scripts/score_scene_checks.py --annotations`). The annotator is renamed
  (`syntax+grammar/3`), so every Hebrew text is re-annotated at the next rebuild: free of
  spend, not of time (see CLAUDE.md on renames). `SCHEMA_VERSION` is unchanged.
- A Hebrew verb's own pointing now picks its conjugation table, per occurrence
  (targum-internal#307, decided 2026-10-03). `אוכל` is `אָכַל`'s present, the past of the
  פֻּעַל `אוכל` and the future of `יָכֹל` letter for letter, so it drew no table; written
  `אוֹכֵל`, it opens on the vowel only the פעל's present does. `paradigms.opening_of` reads
  that vowel, and `Table.pointed_as` keeps a verb only where it has a form in those
  letters whose binyan and tense open on it. It refuses wherever anything else could be
  it: a verb whose binyan cannot be read, any verb outside the lemma's candidates spelled
  alike, the word's own binyan saying otherwise, or the page's present or readings naming
  another verb. Render-time only, from the surface already stored: no annotator rename,
  no re-annotation. The page carries an occurrence's table as `paradigmsHere` only where
  it differs from the word's. Measured over the shelf's current builds (149,521 verb
  tokens): 77.1% → 77.8%, and `אוכל` 102 → 422 of its 828 tokens. The 77.1% counted
  letters-only matches on unpointed text as "settled by pointing", though the page never
  passed a surface; measured with no surface, as the page drew, it is 76.3%.
- A Russian daily or parasha page says the rest of itself in Russian
  (targum-internal#188). A reading names its book the way the Russian shelf does —
  «Числа 4:21-7:89», not "Numbers 4:21-7:89" — and a Hebrew date its month, «19 элуля
  5786», through new `reference.*` and `hebrew-month.*` keys; a name with no key, a
  Mishnah tractate or a special Shabbat, stays as Hebcal spells it. The daily page's
  headline, the line under it, the other cycles, the picture's credit and the cycles the
  shelf cannot carry are Russian too, and so are the parasha's haftarah line and its
  translation credit. Today's page of each cycle and every portion's page now canonical
  to their own `?lang=ru` address, declare their alternates, and are listed in both
  languages in the sitemap. The weekly's description follows the issue's Hebrew
  standfirst with what the series is, in the page's language. English pages read as
  they did, apart from the weekly's description gaining that sentence and a one-verse
  haftarah saying "1 verse".
- Verbs whose conjugation table was a stub are filled in by rule from their root and
  binyan (targum-internal#307). `אָכַל` had ten forms and no `אוכל`; 34 such verbs now
  carry 523 more forms between them. The rule follows the patterns the complete tables
  follow, never changes a form the source has, and leaves a cell empty where it cannot
  tell (the future of `אָכַל`, which could be `יאכל` or `יאכול`). 82 stubs are refused
  because their forms fit no pattern, or because there was too little to go on. In a
  leave-one-out check over 2,382 complete tables, it fills 99.8% of cells correctly from
  three forms and 99.98% from ten. Conjugation coverage on current builds goes from 77.0%
  to 77.1%. `scripts/fill_paradigms.py` writes the shipped table, and the filled forms are
  kept under `filled`, apart from the source's.
- `/about` says its count in English a person would say: "1,174 changes from 31 August
  to 29 September", where it said "1174 changes in the 30 days to 29 September". The
  Russian takes its three plural forms, «1 174 изменения с 31 августа по 29 сентября».
- The English copy, audited end to end (`COPY_AUDIT.md`): 151 catalogue strings and some
  thirty literals rewritten against design.md §6 — mostly claims the code did not keep
  ("One press and you're on the list", "That link has been used", "we can't read scans
  yet", "This is this week's"), refusals without a way forward, singular forms that said
  "words", and team words reaching readers (build, quote, thread, shelf, conversation).
  No behaviour changed. `COPY_VOICE_GUIDE.md` is the checklist for English written from
  here; `COPY_QUESTIONS.md` holds what needs David.
- The arrival opens with a welcome: where you are, what happens next, and an optional
  "What should we call you?" that the greeting uses at once. The connector's card says
  it is optional and has one press, Continue; the bars count only the questions.
- The waitlist's pages say "Thanks for joining", "Confirm your place", "You're on the
  list" and "You're off the list" over sentences a person would say, instead of "the
  waitlist" over every answer — each true for every address it can be said to: a link
  "no longer works" rather than "expired", since a waitlist link has no age limit, and
  joining says an email went out only if the address was not already on the list.
- The sign-in page's foot stands under the door across the page instead of in its
  column, where its columns ran into each other; a long address wraps at its "@"; and
  the line about words following you between browsers is gone.
- targum in Claude and ChatGPT is met on the way in, in four places, each only while the
  connector is open and, inside the product, only to a reader with no connection yet. The
  arrival ends on a card with the address to copy and Open as its press, so the first text
  is still one press away; the first finished section says, once, "Practise the words you
  marked in Claude or ChatGPT"; the banner on Learn is a card with the two steps and the
  address; the front door mentions it twice, lightly, in its list of what you get and in
  the part about talking to targum; and the invitation mail gives it a paragraph with the
  way to `/connect`. The reader's line is said at every finish while there is no
  connection. `/known-ahead` says `connect` for the reader's
  line. design.md §12 (2026-09-28).
- The arrival asks which language a reader reads only where the browser gives a sign of
  Russian (Russian, or a language of the Russian-reading world); nobody else is shown any
  Cyrillic, and an EN · RU switch in the card's corner is the way in for the rest. The
  level question reads "How much Hebrew do you know?". design.md §12 (2026-09-28).
- The mail's English can be edited as notes in `~/Desktop/targum marketing/emails`:
  `scripts/mail_notes.py push` writes one note per mail, `pull` takes the edits back into
  `en.json` and refuses a note that drops a `{link}`.
- The arrival is a page of its own at every width. While a new reader answers the three
  questions, Learn draws nothing else: not the fold of words to work on, which somebody
  who has read nothing has never marked, and not the rail or the sheet. The questions
  stand in one card, the question at 1.5rem, where the reader is drawn as three bars in
  leaf beside "2 of 3"; a picked subject takes the primary's tint and a ring of it, and
  the kitah letter beside each rung sits on a disc in the Hebrew face. Each screen comes
  in on the desk's curve, and nothing moves under reduced motion. design.md §12
  (2026-09-28).

### Fixed
- The week's sheet's meanings above words no longer print over each other, and every
  line of the text is one height while meanings are on (targum-internal#415). A meaning
  could hang past its word, so two short words side by side, as at Genesis 1:2, printed
  "a vacuity" over "chaos"; the word's box is now as wide as its meaning. And a line
  carrying a meaning stood taller than its neighbours, so the Hebrew column ran
  unevenly; every line now keeps the room for one.
- The Hebrew stress gold read an accent written before a holam male — the codex puts
  גָּדוֹל's on the dalet — as stressing the vowel before it, and filed 296 of its 3,000
  words as mil'el that are milra (targum-internal#325). Read now as the holam's, under a
  new corpus name, `tanakh-taamim-v2`, so the old row does not seem to move: the default
  is 0.7630 there against 0.6863 on the first gold. phonikud already read these words
  right; only the eval was wrong.
- A deploy no longer stops at the install when somebody has run a targum command on the
  box as root. Such a run, `--help` included, leaves root-owned `__pycache__` inside the
  tool's environment, and the service account could not remove it: "failed to remove
  directory .../tools/targum/lib: Permission denied", on 2026-09-29. `deploy.sh` hands
  the environment back to the account before the install.
- What the copy audit found the code saying wrongly (`COPY_QUESTIONS.md` 2–11, 14, 20–23,
  28; design.md §12, 2026-09-28). The build page says "We're making it" to a queued build
  and one still being costed, not "We can't make this one". Add shows the upload door's
  own sentence for a refused file instead of blaming the connection. Your Progress says a
  language has no word list rather than "Nothing marked yet", and its empty state sits
  above the foot. On a hosted box a link refusal is the reader's sentence for its status,
  never "HTTP 403", curl or an operator's hint; errors mid-build are said in the reader's
  language with their hint. A closing account is told how to keep it at every sign-in
  door, and an uninvited address is pointed at the waitlist. Ticking a translation
  language again writes its translations back into the readers, as /you promised. The
  sign-in page says which Connect it is finishing, and says so when one was lost. Learn's
  Suggested door says the known share once. Every press that spends says its cost beside
  it, and the description search no longer prices a chat turn. Signed-in readers are not
  pitched the waitlist on the weekly, parasha and daily pages; an archived issue is not
  "this week's"; the waitlist and series-stop pages have their own titles, and the stop
  page names its series. The contents page and the ready email say Read, Listen or Watch,
  and a scan offers "Read the 12 pages".
- The arrival opens a text the reader can follow. The rung picked a row by its place in
  the subject's list, so the one row filed under a subject was every rung's answer, and
  "Just starting" opened a vav article. It reads the rung each text was written for now,
  and takes the hardest at or under the rung said; a subject whose texts are all more
  than a rung past it gives way to the next; and where no subject is left, the rung
  chooses from the modern shelf, ahead of whether a text can be heard.
- A Russian public page says its title and description in Russian (targum-internal#188).
  The shelf, the text pages, the parasha and the daily cycles took both from English
  whatever language the page spoke, so a search result for a Russian page read
  "Library — targum" over a Russian body. They come from the catalogue now, and so do
  the shelf's heading and the link back to it; the names a calendar spells (a portion, a
  day's reading) stay as it spells them.
- The reader's keys card lists two sets of keys it left out: with the recording's track in
  focus, the arrows go back and on five seconds and Home and End go to its ends; with the
  picture's Move or its size handle in focus, the arrows move or resize it, further with
  Shift. Both only ever worked and were never said (targum-internal#341).
- A deleted account's finished-section rows were not deleted with it: the purge named its
  tables by hand and `section` was never added to the list. A test now asks the database
  which tables name a person, instead of a list that can go stale.
- A reader's credits can be reached on a phone. Who read a recording and under what
  licence, and what worked out the dictionary forms and the vowel points, stood at the foot
  of the keyboard-shortcuts card, which a window under 60rem does not show until a key is
  pressed. So on a phone a CC BY-SA recording could be played and saved from a page that
  never said whose it was. They are at the foot of the text now, at every width, on the
  last page beside the pager, and the recording's credit is also beside "Save the audio"
  in the phone's menu. The keys card holds the keys (targum-internal#342).
- On a local serve the bell, the followed series, the conversation's list and the palette
  were refused on every desk page. Each reads the page's key once, as it loads, and the
  page set the key at the foot of the body. The key is set in the `<head>` now, before
  the nav. The hosted box has no key and was never affected (targum-internal#343).
- The reader's keys button says "Keys". It was a `?`, which a stranger read as help and
  which opened a table of keyboard shortcuts. The `?` key still opens the card. The
  button keeps the mark behind ⋯ on a narrow window, where the row is already named, and
  under 75rem, where the bar has no room for a word
  (design.md §7 and §12, targum-internal#338).
- Transcribe on part two, three or four of an upload does something. The part door
  answered "ready" whenever the part's transcript was on disk, and the page reloaded onto
  the same "not transcribed yet". That happened whenever the hearing had landed and the
  page had not: a build still translating the part, a build the box killed at the words,
  or the next-part prefetch, which fired the moment a waiting part's page opened and
  bought the part after it. The door now asks whether the page can show the part, follows
  a build already on its way, and rebuilds a heard part without paying for it again. It
  also buys the part on the page pressed rather than the part with the page's number, and
  a waiting part's page no longer buys the next one. A part that was heard but never
  translated had a Translate button that went to the same door and did nothing too.
- A whisper transcript no longer loses stretches of speech. A segment was dropped as
  invented whenever its no-speech probability passed 0.6, and on Hebrew that number runs
  high over plain speech: on a ten-minute interview two minutes read 0.90–0.98 while
  whisper was sure of every word, and 463 of 1,283 words were thrown away. A segment is
  now dropped only when whisper is also unsure of it, as its own decoder does. Parts
  already transcribed keep their gaps until they are heard again.
- Learn opens without a long blank wait. The page draws once the shelf answers, and the
  shelf re-read every text's document, segments, translations, annotation and audio
  manifest on every request: 65 MB of JSON for a shelf of 163, 31.5 s on the live box once
  those files had left memory. Each row's answer is now kept in `shelf.json` beside the
  reader, stamped with the size and time of the files it came from, and worked out again
  only when one of them changes. The first open after the deploy is still slow once per
  shelf. Chat turns, which ask the same shelf, get the same saving.
- A Global Voices post in a language other than English loses its translators' notes on
  what language each link opens in, such as "[en, come tutti i link successivi, salvo
  diversa indicazione]". The extractor dropped the link and kept the note in the sentence.
  None of the five Hebrew Global Voices rows has such a note, so none changes.
- A line break in a web page, an EPUB or a Wikisource page reads as a space. `lettura<br>rende`
  came out as one word on the EU's easy-read pages. The URL ingester is `url/5`: one
  catalogue text changes, a Hebrew Wikinews article whose reference line read
  "2022מסכי", and it is read again on its next build.
- `targum build --translation` takes a link or a named source (`gutenberg:1232`) as well
  as a file. It was read as a path, which turns `https://` into `https:/`.
- A catalogue row is built in its own language on every path. `targum seed` passed no
  language, so an Italian row was detected from its script and seeded as English, with
  its words handed to a lemmatizer that refuses Italian. The seed, `targum build` of a
  catalogued source and the server's builder now pass the row's language whenever the
  person or the door did not name one.
- A book-length word buy in French, Russian, Italian or Yiddish keeps each batch as it
  returns. One failed call used to throw away every batch already paid for.
- A Wikisource work split into subpages builds from its name. `wikisource:it:Cenere`,
  `Cuore (1889)` and `Il Principe` said "no readable text" and `Novelle rusticane` came
  back as thirty words of titles, because each is a contents page. A page that links two
  or more of its own subpages and has almost no words besides is now read as the work:
  each subpage in the order the page lists it, under its own heading, without the wiki's
  edition box and chapter bar. Every page with text of its own reads exactly as before,
  and the fetcher is `wikisource/3` so a contents page ingested as its titles is read again.
- A recording built with a transcript is read in the language the transcript's name
  gives (`abc123.it.vtt`, `it.vtt`), or the `language` in a yt-dlp `.info.json` beside a
  local video, where `--from` was not passed. Before, it was read as Hebrew. A subtitle
  file built on its own takes its language from its name the same way, and a plain-text
  transcript is loaded in the recording's language, so the aligner's model is the
  language's own. Where nothing names the language the build still reads Hebrew, and the
  command line now says so and says to pass `--from`.
- `targum video curate` carries a video's own English, aligned from
  `--translation en.vtt`, and prefers it to a bought one. Before, it skipped every
  aligned translation and refused the folder with "No English".
- Subtitle cues decode HTML entities. `&nbsp;` between two sentences in YouTube's
  Italian tracks glued them into one row.
- `python -m targum.cli video curate` and `video list` exist. The `__main__` guard sat
  above them, and a test now keeps it last.
- Italian quotations stay on one row. A full stop or an ellipsis inside «», “”, straight
  quotes or a dash-set line of dialogue split the quotation in two, and a straight `"`
  opening a sentence after a full stop was read as closing the one before, gluing the
  two. Italian is the one language this is turned on for (`cased.QUOTING`); the cased
  rules are `cased-rules/2`, and Hebrew splits exactly as before. On the Italian shelf it
  changes 467 blocks and no curated video. A text already built keeps its segments.
- A conversation reopened while targum was still answering now shows the answer. The
  model's tool results were handed to the page as if they were your lines: each was drawn
  as an empty grey bubble, and each told the page nothing was still being answered, so it
  never picked the answer up again and waited for good on one the server had finished.
- The commonest-words list no longer offers English to a language wordfreq has no list
  for. Asked for Yiddish, wordfreq answers with its fallback list instead of refusing,
  and `common_words` only caught a refusal; it now checks the language is really there.
  And the "Words you may already know" panel stops showing Hebrew words on a page in
  another language: it asked the switcher about Hebrew alone, so its answer was always
  Hebrew.
- The chat's shelf says when each text was last opened and finished. "What was the
  last targum I read?" was answered "the list does not keep times" (2026-09-08); the
  reader's own sync had always clocked every open and every chapter finished, and only
  the tool left them out. `search_my_shelf` comes back newest opened first with
  `last_opened`, `days_since_opened` and `finished` on each row and `now` beside the
  list, so the model can count as well as read.
- The chat takes a language however the model names it. `quote_build` refused
  `"to": "English"` and `"english"` and took only `"en"`, and each refusal cost the
  reader a whole model round trip; a name, a code in any case and a regional tag now all
  mean the code, and the tool's schema lists the codes (targum-internal#270).
- The haftarah, under the reading on `/parasha`. Hebcal was already returning it on the
  call the calendar makes and the parser was throwing it away; now it is parsed beside
  the aliyot — `Reading.haftarah`, not a third `ReadingKind`, because it is the second
  reading of a Shabbat and not a kind of one — and cut from the Prophets already on the
  shelf into a one-section reader of its own, keyed by what it is (`isaiah-61-10-63-9`)
  since the same one comes round on more than one Shabbat. Every one of the twenty-one
  books is built, so nothing is ingested and nothing is spent. The page frames the
  week's haftarah on the page that means this Shabbat — a Shabbat Rosh Chodesh or
  Chanukah reads the special one, and the dateline says why — and the portion's own,
  decided across every occurrence in the corpus span, on a portion asked for by name;
  a festival Shabbat shows the festival's, and the two schedules each carry theirs. The
  Sephardic reading Hebcal returns is recorded on the week and the portion and is not
  shown: no rite chooser. One chanting-marks switch reaches both frames
  (targum-internal#201).
- The chat's search of the publishers' feeds pulls them side by side and keeps them
  five minutes. It pulled nineteen feeds one after another, each allowed thirty seconds:
  a "tech news" turn spent 21 s in that one step. A feed that misses the eight-second
  budget is named as late and lands for the next search, and a feed that would not
  answer is left alone for two minutes (targum-internal#272).
- At the foot of a finished section, which words cost the reader the most
  (targum-internal#174). Every card opened on a word is counted, by lemma, in the
  browser (`targum:cards:<language>`), and the foot says which words were looked up
  in this section and how often each had been looked up before — "looked up twice
  before", "the first time" — which words were read here without a look-up having
  been looked up in an earlier text, the half that shows progress rather than debt,
  and offers the two or three most-repeated to the reader's list, one press each. No
  score, no percentage, no red, nowhere: there is no oracle for "did you understand
  this sentence", and counting look-ups is counting what is there. Names and numbers
  are never counted.
- The ledger's increment is delivered, not visited (targum-internal#175). The foot of a
  finished section says what moved while it was read — the delta, then the standing it
  moved to: "3 newly known · 412 known", "day 12 reading" — for the counts that moved
  and no others, in the ledger's own treatment, under the tally, in the flow, with
  nothing to dismiss and nothing in motion. Where the ledger stood when the section was
  first opened is kept in the browser (`targum:foot`) and read back on Done. And the
  streak: the longest run of reading days is counted once, in `charts.js`, shown on
  /progress beside the other counts, and announced at the foot on the day it rises and
  on no other day; the current streak is refused, not unbuilt — design.md §12 records
  the decision of 2026-09-03 and `test_brand.py` pins the absence. The reader now
  carries `charts.js` for the arithmetic, so three pages cannot disagree about it.
- A chat line targum was answering when it restarted says so. Start-up told a build
  the truth and left the reader's line at "working" for good, so a page opening it
  again waited on an answer nobody was writing, or drew an empty one. It now reads "We
  restarted while we were answering. Ask again." (targum-internal#269).
- The Hebrew of a daf, from Sefaria (targum-internal#193): `sefaria:daf:<tractate>` is
  the tractate's Mishnah in the Romm edition, the daf's own printing, a perek a heading
  and a mishnah a verse; `sefaria:Rashi on <tractate>` and `sefaria:Tosafot on
  <tractate>` are the Vilna commentaries, an amud a heading and a comment a paragraph,
  every block carrying its address — `Mishnah Berakhot 1:1`, `Rashi on Berakhot 2a:3:1`
  — in `ref`. Public domain or nothing: the shelf admits CC-BY and CC0, a daf does not,
  because a daf is one object. Never `fill_in_missing_segments`. Rabbinic, not
  scripture, and pointed by the pipeline because Romm and Vilna print no vowels. The
  order of a daf is a contract this side owns: the perek table from Sefaria's index,
  and `reading_key`, which puts a mishnah before the Gemara on it and ends a perek
  mid-daf where the index says, for #192's Gemara blocks to sort into.
- Somewhere errors are recorded, other than the journal (targum-internal#24). Every
  exception a request or a build swallows — a route that raised, a build that died, a
  look-up that failed — is written to `incidents.jsonl` beside the output, a ring of the
  last two hundred, and the back office lists them newest first with the traceback's
  tail behind a disclosure. A file on the box rather than a vendor, for the reason the
  back office gives for itself; never a request body, an address or a reader's text.
- A chat turn says what we are doing while it works, and never waits for good. The page
  says "We're searching the web…" or "We're reading the page…" as each step starts, and
  "We're still working on it…" after twenty quiet seconds. The server ends a turn after
  four minutes and says "We took too long to answer that. Try again."; the page stops
  waiting a little after, and shows an answer that did arrive (targum-internal#271).
- The reader switches between renderings (targum-internal#199). A document has always
  been able to carry several translations; the page now draws every one it carries —
  each with its own language, direction and coarse marks — and a text with more than
  one gains a switch in the bar, drawn the way the levels are: one pill, a fill under
  the live one, named by language where the languages differ (Aramaic beside English
  is what a reader doing shnayim mikra is choosing between) and by the rendering where
  they do not. Hebrew against Onkelos runs right to left on both sides and against
  English on one, and the cells say so per rendering. The choice is kept per text, the
  way the vowels are; a text with no choice yet opens on the language the reader said
  they read into (`targum:into`) when it carries one. A chapter one rendering has and
  another does not is drawn from the one that has it, with the other's button
  disabled rather than emptying the column. Switching writes only the translation
  cells: every mark, phrase and offset is measured against the bare source text and
  none of them moves. A text with one translation renders exactly as before, and shows
  no switch at all.
- Modern Hebrew is pointed by DICTA's menaked (`dicta-il/dictabert-large-char-menaked`,
  CC BY 4.0), measured first against Nakdimon on two held-out sets — DICTA's own
  Wikipedia test corpus and pointed prose and poetry from Project Ben-Yehuda by authors
  neither model was trained on — and better on both: +1 point on vowels per letter, +2
  to +4 on exact words, a perfect consonant skeleton, and the qamats qatan that
  Nakdimon never writes and phonikud needs to say כָּל as `kol`. Gated by register:
  scripture and the pinned editions reach no model, as before; the rabbinic and
  medieval shelves stay on Nakdimon, whose card the menaked's says it is not for; the
  revival and modern shelves and every upload go to the menaked. The weights are 1.2
  GB, fetched by `targum models fetch menaked` (or `fetch he`, with the annotator's)
  and never in a build: a machine without them points with Nakdimon and says so. The
  vocalizer's name is the cache key, so a text Nakdimon pointed is pointed again on its
  next build or `rebuild --words` — about 0.3 s a sentence on a box without a GPU,
  which is why a deploy that carries this is scheduled rather than run. `SCHEMA_VERSION`
  is untouched. The reader credits DICTA for the vowels where it made them, beside the
  credit for the words; `LICENSING.md` records the licence, the measurement and the
  gate. `scripts/measure_pointing.py` and `evals/ledger.jsonl` (stage `vocalize`) hold
  the numbers (targum-internal#148).
- The correction store, door 1 (targum-internal#164). Every human judgement about a
  word is written down with its provenance — what stood before, what stands after, who
  decided (a role, never a name), the licence the judgement is held under, and the
  sentence they saw — in a `correction` table of the accounts store (schema 14).
  `targum correct <lemma> --meaning …` and `--forget` apply the author's hand to a
  gloss and keep the judgement, where deleting a cache file by hand used to throw it
  away; a grounding at a reader's tap writes the bare sense that stood and the grounded
  one that stands; `targum corrections` lists them. The editor's and the reader's doors,
  the harness export and the notice text are the rest of the card.
- The chat is handed a few sentences a Hebrew speaker wrote, inside the reader's own
  words, to write in their idiom rather than translate from English. They are Tatoeba's
  (CC BY 2.0 FR), only those by contributors who declare Hebrew native, lemmatized once
  by `scripts/tatoeba_pool.py` into a pool the box reads (`TARGUM_EXEMPLARS`, or
  `exemplars.jsonl` beside `sources.json`); a box without the file has none. Six a turn,
  after the cache breakpoint, first claim to a sentence carrying a word the reader saved
  lately, originals before translations, drawn afresh each turn; retrieval is local and
  buys nothing. Two evals draw on the same pool: `scripts/eval_recast.py` scores the `> `
  recast line against a native speaker's rendering of the same English (stage `recast`),
  and `scripts/eval_grading.py --pool` draws its openers from sentences inside the
  synthetic reader's list, so the outside share can be read per rung. `LICENSING.md`
  records what is taken, what is owed and where the credit is given.
- A picture is a text. The `+` on the box and the Add page take a screenshot, a phone
  photo (HEIC included) or a PDF with a text layer, and several pictures chosen
  together are the pages of one text in the order chosen. Pictures go up the chunked
  door and are read by the model at the price quote — the one spend before a card,
  reserved against the same rails a build is claimed on and settled to what the API
  charged, cached by the picture's bytes so nothing is read twice, capped at thirty
  pages (targum-internal#217). A PDF's text layer is read by `pypdf` and costs
  nothing; a scanned PDF is refused by name and stays on #197. The card shows the
  first lines as read and how many lines could not be read clearly, so what will be
  built is seen before the press. Every block carries its page as `ref`, and a line
  with no Hebrew in it is marked English so the lemmatizer leaves it alone. New
  `bring` extra: `pillow`, `pillow-heif`, `pypdf`.
- A chat photographed off a phone is a dialogue. A screenshot of WhatsApp, Telegram,
  SMS or the like is read as turns — the model writes `[conversation]` and one
  `name: message` a paragraph — and drawn the way the shelf's own scenes are: the
  speaker beside the line, out of the text, never pointed, counted or read aloud.
  The chat is named on the shelf for the other side. A turn's speaker now reaches the
  reader from its block, so a saved conversation shows who said what without a
  recording too.
- The box is the front door. Learn carries one field under the ledger's own sentence —
  a request, a link, a file by its `+`, a word you are stuck on, Speak where the browser
  records — and a line typed there opens a conversation and goes to it, with the new
  conversation's id in the hash so the page opens that one. Nothing is answered on
  Learn. Chat leaves the nav, a day after it joined it; Upload leaves the corner and is
  the `+` on the box, on both pages that carry one. The box is one file
  (`_composer.html.j2`) and push-to-talk is one script (`speak.js`), shared by Learn and
  the conversation page, because two copies of a box drift the way two copies of a nav
  bar did. A reader whose every text is scripture is not written Hebrew at: their
  conversation is opened in English, about the text, and no microphone is offered —
  `Library.talks` decides it from the shelf, and `/readers` and `/chat/list` both say
  it as `talk`. `design.md` §12 records the day's decisions and what was cut ("The front
  door is a question").
- Bringing a text is one press. The `+` on the box — on Learn and on the conversation
  page — takes a file or a recording, sends it up the way the Add page does (a
  recording in pieces, anything else whole), prices it with `/prepare`, and draws the
  same card the model's quote draws as a turn in the thread — a file is held in the
  box as a chip until Send, and Send is the press: the text builds and opens when it
  is ready, with no conversation started for a bare file or a line that only says
  "open this"; a line that says more is said with a note of what was sent, and the
  card follows it in the thread as the build's progress (2026-09-07) — with no model
  in the loop; the card's button is the spend, and its "More options" is the Add
  page, kept for the two things only its form can say — a translation of your own, a
  transcript of your own. A link goes in the field like anything else said to targum.
  The upload, the price in the reader's time, the plain words for a build's progress
  and the card are one script now (`bring.js`), shared by the Add page, the box and the
  conversation page, because two answers to one question drift.
- The thread is drawn as the text it becomes. In Hebrew, every line the model writes is
  read the way a text is read the moment the reply is whole — the same lemmatizer a
  build uses, warmed when the chat's workers start (`chat/record.py`; measured first:
  a line in about sixty milliseconds, a turn in a fifth of a second, on a laptop) — and
  each word comes back to the page with its dictionary form, its band and whatever
  meaning the glossary already holds, as a `words` event before `done` and kept on the
  reader's turn for the page that comes back. On the page a word takes its state from
  the reader's own ledger: known bare, learning underlined, not met marked and counted,
  a name left alone; a tap says the form and the meaning or offers to look it up, the
  reader's own press and spend. The foot of the thread says how long the conversation
  has run, how many words the reader has not met and what share they knew, and carries
  Save as targum — `POST /chat/save`, the reader's press on the same quote the model's
  own save hands the page, and only a quote. Every turn records what share of its
  vocabulary lay outside the words the model was given, for the eval (#213), and the
  page claims nothing from it yet. What the reader saved lately — words a newspaper
  would use, and phrases — rides in the ledger block, and the model is asked to bring
  them back and, once, to ask the reader to use two, never as an exercise.
- A word tapped is a question half-asked. The gloss card gains one more working action,
  Ask: a question typed there goes up with a note of where the reader is — the text, the
  section, the sentence, the word — and the answer streams back into the card the way
  the conversation page's do, in English, about the text: what the form is, why it is
  that form here, where they have met it before. Two questions, then "Continue in chat"
  carries the conversation on. The note rides in the turn the model sees and not in
  what the page shows back, it is strings and capped, and it opens the conversation in
  English whatever the shelf would have offered; on scripture the model is told to
  write no Hebrew of its own beyond what the text says. The reader still fetches
  nothing it did not already: the card talks to its own origin the way a gloss does.
- targum has a chat. `/chat` is a door on the rooms that already exist: ask what to read
  next and it answers from the library measured against your own words; ask what you have
  read and it answers from your ledger; ask about a build and it reports where it has got
  to. Seven read-only tools behind it — the catalogue, your shelf, your vocabulary, your
  progress, a ranked suggestion, a build's state — declared once (`chat/tools.py`) so the
  same list can be served over MCP later, and every one reads whose shelf and whose words
  from the session, never from an argument. The model may not spend: no tool in this slice
  buys anything, and the seam for the ones that will is drawn (`spends`, `needs_consent`).
  Answers stream as server-sent events on the same origin under the same policy every
  page takes — `connect-src 'self'` did the work it was written for, and nothing in
  `POLICY` moved. A conversation is the server's, unlike words and reading position, and
  it travels in the account export and leaves with the account. Every turn is a `job` row
  of kind `chat`, so the rails see it: a chat rail of its own (`CHAT_BUDGET`, a dollar a
  day, a rate limit like the account's) and the account rail both count it, and the refusal
  names when it lifts and never implies reading is used up. The ulpan ladder the progress
  page draws is now in Python too (`level.py`), pinned against the browser's `charts.js` by
  one fixture, so the chat can grade what it writes — and is told in as many words never to
  quote the rung as a placement. `design.md` §12 records the reversal this is
  ("targum speaks back"), and the roadmap's "Not building" line carries the decision.
- And the chat can price a text. `quote_build` is `/prepare` reached by a sentence — a
  link, a podcast episode, a YouTube address, a Gutenberg or Wikisource id, or a library
  text by id — refused on exactly the grounds the Add page refuses, and it costs nothing:
  `Library.prepare` is the free half of the quote-then-consent seam. The quote reaches the
  page as its own event and is drawn as a card from the job's state, never from what the
  model said about it: title, sentences or chapters or hours of audio, how long it will
  take in the reader's time and never in money, and one ink button. The button posts to
  `/build`, the same door the Add page's button posts to, so `Handler._build` stays the
  only path to `Library.claim` and the model holds no tool that could press. `my_hours`
  says how much of the month's audio allowance is used and when it returns, in hours.
- And it can find things. `describe_source` says what is at a link before it is quoted —
  a video's length, its audio language and whether it has Hebrew subtitles somebody wrote
  (from `yt-dlp -J`, never the video); an episode's length and whether a transcript comes
  with it; an article's words and how much of it is Hebrew — with the licence recorded and
  the screen's flags as advice, never as a refusal: a reader's own import is refused only
  at the fetch door, on format, or on the rails. `search_sources` reads what the publishers
  this box knows have published lately, from a private `sources.json` the way the
  catalogue is a private file, and a box with none simply has nowhere to look. Where
  `TARGUM_WEB_SEARCH` is on, Anthropic's server-side search rides along, held to those
  publishers' hosts and the public-domain fetchers' for relevance; a search is bought per
  search and `Usage` now counts it, so a turn that searched settles for what it cost.
  `LICENSING.md` says the private-import posture in one paragraph.
- What a reader asks for feeds the shelf. Import is not gated on licence; promotion is,
  and `promote.py` is the one place the licence recorded at ingest is read. After every
  build the queue finishes, a private text whose source stands `free` or `owed` is
  proposed for the catalogue — `unknown`, which is most of the web, stays private for ever
  — and a person accepts or declines it in the back office, which gains the list with the
  register and kind to correct and a credit an `owed` licence must carry before the merge
  will take it. The public-domain fetchers promote themselves on completion, because their
  licence is certain by construction. Accepting moves nothing: the reader's folder stays
  theirs, the translation they paid for is re-keyed into the shared cache the way `targum
  warm` does it (the two now share one body), and an entry is merged into the catalogue
  file with the model named so the next reader's build is free. `Entry` gains `licence`
  and `credit`. The back office also lists what was wanted — a library search that found
  nothing, a link a reader had described — as counts, never who.
- targum talks. Every conversation is in Hebrew, whatever the reader writes in: the
  model writes in pointed Hebrew with the English under every line and recasts whatever
  the reader said in another language into Hebrew first — the shape a targum has, so the
  record can be read back (that reading-back is the next slice). It opened with two
  modes, Find and Hebrew, and lost the first on 2026-09-06 after a reader who asked in
  English for something to read was answered in English: there is one conversation, and
  it is in the language being learnt. A text the model finds is handed over as its path
  on a line of its own, which the page draws as an ink door the reader presses — the
  model cannot open anything, and no longer says it has. And the reader's own words
  come back into the conversation by where they stand — met once, learning, nearly
  known, and a few known ones marked known longest ago — from the whole ledger and not
  only the week's, a different slice each turn, so a saved word is met again when the
  reader is not reading (2026-09-07). The chat also knows what the product around it can take
  and how a reader gives it — the + beside the box, a screenshot of WhatsApp, a phone
  photo, a PDF, a recording, a link — and that a picture is read into words before it
  reaches it, after a reader who asked whether they could send a screenshot was told
  twice that targum reads only words, sent it, and was told no picture had arrived. The
  note with a sent file now says what was sent, and the pictures themselves are seen in
  the thread as the reader's own turn. It is handed the reader's own known words
  from their ledger and, under them, the commonest words of the language at the first two
  bands, and asked to stay inside them with one new word a sentence; the contract is
  `chat/hebrew.py`, and whether a model can hold to a list is measured by
  `scripts/eval_grading.py` before any page says "at your level" — no page does yet.
  Conversation comes out of the eight hours: a typed turn is converted to seconds at
  120 words a minute (the measured conversational rate, reconciled against the 89 of
  read-aloud literature and the 150 the cost estimate deliberately sits high at), a
  turn's seconds land in the same monthly sum a recording's do, the refusal at the cap
  names audio and conversation together and the date they return, and the chat page shows
  the hours used beside the list before the cap is met.
- And a conversation can be read back as a targum. Ask to keep it and the chat writes it
  down in your own home as a `.chat` file — always Hebrew on both sides, because every
  reply now opens with your own line recast into Hebrew (as you wrote it if it was right,
  corrected if not, translated if you wrote in English) with your words as its English —
  and prices reading it back on the same card a build gets. The English is carried, so
  nothing is bought for translation; the words are glossed like any text's and land on
  your ledger. It is addressed by path, never a scheme: `dialogue:` and every public
  prefix share a cache with no owner on the key, and a conversation filed under one would
  have been reachable from another account. The shelf files it as a dialogue, and a
  conversation is never proposed for the catalogue.
- Push-to-talk, and called that. A Speak button records a line, sends the
  clip up as itself, and the same transcriber a recording gets writes it down and asks it;
  a Hear button on each answer reads it aloud, made once and kept. The clip's seconds come
  out of the eight hours in both directions — the microphone's off the recording, the
  voice's off the WAV the API returned, never off the text — and a spoken line is metered
  once: the turn it becomes counts the reply alone. The Gemini client moved out of the
  gitignored weekly into a public `speech` module so the box and CI can run it; its price
  is in no table yet, so its seconds are counted and not charged, and the module says so.
  Seconds to first sound, not a conversation, and nothing on the page pretends otherwise.
- `targum mcp` adds the same tools to Claude Desktop or Claude Code over stdio. The one
  registry the chat runs on is served as it stands — the library measured against your
  words, your shelf, your ledger, a suggestion, a build's state, a link described, a text
  priced — and nothing that spends: a quote over MCP is information, and the press that
  starts a build stays on the page where the card is. The `mcp` SDK is an optional extra,
  so a plain install carries nothing for it.
- Hebrew sentences are drawn by rule, and no Hebrew text passes through Stanza at any
  stage. The annotator swap moved every Hebrew word off Stanza's NonCommercial models and
  left every Hebrew sentence boundary on them — DICTA takes a sentence at a time and
  publishes no splitter — so `LICENSING.md` was claiming more than was true.
  `segment/hebrew.py` splits Hebrew on terminal marks with four rules read off the shelf:
  a closing quote or parenthesis after the mark keeps the quoted sentence inside the one
  quoting it, a dash after it keeps a speech tag with its speech, an ellipsis alone is a
  pause, and an initial's full stop is not an end. `HebrewSegmenter` holds Stanza for
  every other language the way `DictaLemmatizer` does, `StanzaSegmenter` now refuses
  Hebrew outright, `Annotator()` with nothing passed reads Hebrew through DICTA rather
  than Stanza alone (the gloss command, the weekly's gauge and two scripts reached that
  default), and `targum models fetch he` no longer fetches Stanza's Hebrew models at all.
  Measured on the 47 readers before switching: the rules and Stanza differ at 2,768
  boundary positions of the 18,490 Stanza drew (15.0%), almost all of them exclamation
  marks Stanza had never split on, plus 327 speech tags it had cut off their speech and
  closing quotes it had put at the start of the next segment. Review before landing
  found that `DictaLemmatizer` routed on the raw language tag, so a text whose front
  matter said `he-IL` or `iw` had been reaching Stanza's Hebrew models since the swap;
  it routes by code now, and the Stanza lemmatizer refuses Hebrew as the segmenter does.
  The DICTA weights load once per process rather than once per annotator, since the
  weekly's gauge builds one per attempt. A text on a shelf keeps the segmentation it was translated under, because the
  pipeline reuses `segments.json` by document hash and the segmenter's name is a record
  rather than a key; `scripts/measure_segmentation.py` reproduces the count and prices
  what a forced rebuild would re-buy (targum-internal#146).
- The shelf can say "video", and a YouTube address is turned away at the paste. A row says
  one word, `video` or `audio` and never both, since a video can be listened to as well;
  the fact is derived from the recordings the way `spoken` is rather than written into the
  catalogue by hand, and the Media select gains "With video". An address pasted into the
  add box is recognised as it is typed and again at the button, before any request leaves,
  and the notice names the two doors that do open: upload the file, or run `targum build`
  on the reader's own machine, with the command behind a Copy button. A video that was
  fetched now links home at the line being read. The build adopts what it fetched, so the
  address was being lost; the manifest keeps `home` and the part's offset into the whole
  video, and the page carries one canonical watch link, never for an uploaded file, which
  has no home to link to (targum-internal#136).
- `LICENSING.md` records the Nakdimon weights. The diacritizer's model ships inside the
  `nakdimon` wheel, so every install of targum redistributes it and the box serves its
  output commercially. The wheel carries one licence, MIT; the model file has no licence
  of its own and no model card; and MIT grants distribution and sale so long as the notice
  travels with any copy. The training corpus has no licence at all, and no one in its
  chain attached a NonCommercial term, which is the Stanza question in a weaker form. Both
  are written down in the section that already holds that caveat. No code
  changed (targum-internal#31).
- `scripts/screen_candidates.py` screens a recording before it screens its words. A
  YouTube address, or a local recording with a subtitle file beside it, now passes three
  checks before Stanza is loaded, all of them taken off the artefact rather than its
  metadata: the audio track's own language tag, how much of the recording the subtitle
  track covers (the last cue's end over the duration, gated at 95%), and words per minute
  as a flag outside 80–118. Twelve licence-verified Khan Academy videos had passed the
  text screen; one served another video's subtitles and stopped at 54%, and it is now
  rejected without anybody watching it. A cue at 99:59:59 is dropped and counted rather
  than read as a hundred hours of coverage. The parsing and the gates live in
  `targum.screen`, tested on fixtures, and nothing is downloaded but metadata and the
  track. Each output row carries `reader_publishable` and `corpus_exportable`, both off
  the one verdict `licensing.py` computes — which gained `derivatives`, the question a
  free reader asks and export does not — and rows are ranked so the band the shelf is
  thinnest in comes first (targum-internal#139).
- A block can name its own language. Daniel and Ezra turn into Aramaic mid-book and
  back, and a document with one language sent their Aramaic through the Hebrew pipeline:
  Stanza tagged half of it as names and read יָת as the Hebrew verb נתן. `Block` and
  `Segment` now carry an optional `language`, meaning the document's where absent, so
  every artifact on the shelf still parses; the Sefaria ingester marks Daniel 2:4–7:28
  and Ezra 4:8–6:18 and 7:12–26 as `arc` (Daniel 2:4 whole, a verse being the boundary a
  block allows; Jeremiah 10:11 and the two words of Genesis 31:47 are below the block and
  stay Hebrew, and the ingester says why); the segmenter never hands such a block to a
  model built for another language; and the annotator leaves it without tokens rather
  than glossing it as Hebrew, so no card claims a dictionary form the word does not
  have. Difficulty counts nothing for it. The reader draws those rows under `lang="arc"`
  and names the turn once above the row where it happens — "Aramaic" over Daniel 2:4,
  "Hebrew" over 8:1 — so the switch is seen rather than inferred from words that have
  stopped answering to a tap. The rule is in the annotator's name, so both books are
  read again on their next build, for nothing (targum-internal#66).
- The word card says which Hebrew a word belongs to. The register table has ridden
  beside the lemmas since it was built and nothing read it; the card now draws the line
  it was built for, on the few cards where scripture and the street disagree about a
  word and on no others: "biblical · rare today" in a Tanakh, "biblical · an import
  here" in a text written today, "modern · not in the Tanakh" the other way about. The
  words live in the reader, so rewriting them re-annotates nothing (targum-internal#140).
- An Anki deck from the word list. The two CSVs were a spreadsheet's files, and most
  people learning Hebrew keep the words they are drilling in Anki, where a card wants
  what a column cannot carry: the word as it is pointed on the page on the front, and on
  the back its meaning, the sentence it was first met in, and for a verb its root and
  binyan. A Masoretic text gives its cards the vowels without the chant. Tab-separated
  under Anki's own header lines, so it imports as it is, filed under `targum::` and the
  text's name; phrases make a deck of their own, the way they make a file of their own
  (targum-internal#39).
- `targum preflight` on the hosted box no longer asks for `yt-dlp`. The box never fetches
  from YouTube — the paste is refused by name, and the fetch is a command-line door — so
  the check passes there with a note saying so, and warns only where the door is real. A
  warning that is always wrong is one nobody reads, and it was taking the real one beside
  it, that backups never leave the box, down with it (targum-internal#143).
- `NOTICE`, at the root and in the wheel. The AGPL is a licence on the code and reserves
  nothing about the name; the notice says that "targum" is the project's name and that a
  derived product or service is not called by it. `LICENSING.md` sends a reader there
  from the sentence that grants the code (targum-internal#79).
- A reader that starts before its store has answered can no longer bury the better copy
  it never saw. The store gives the shelf half a second and starts the page on
  `localStorage` regardless, which on `file://` is the copy that may have lost a write;
  a write out of that page then carried a fresh stamp, and from that moment the shelf's
  newer copy could never win again — a slow read became a permanent bad write. A page
  started that way now keeps its writes below the shelf's copy until recovery lands and
  shows the shelf was not ahead, and the shelf wins on the next opening if it was. The
  same recovery now also sends the shelf a write whose mirror never committed, which is
  what leaving a page mid-write used to cost (targum-internal#154).
- `targum measures` — the six beta questions, counted off the store. Whether a reader
  comes back for a second text, by the week they joined; the first text and whether it
  was finished; which of the two shelves each reader has opened and how many readers of
  the Tanakh have opened anything else in Hebrew; days since joining; and texts finished
  and days read, per reader per month. No model is asked and nothing is spent. Three
  answers are not in the store — a play never reaches it, the place in a text is kept in
  the browser and never synced, a session carries no device — and the report says so in
  each answer's place, with what would have to be recorded first, rather than printing a
  number that stands for something else. Nobody is named in it (targum-internal#50).

### Added
- You can talk to targum about the text you are reading (2026-09-11: "when I am reading
  something I want to literally be able to chat with it"). A served reader carries the
  same pill and drawer every chrome page has; the reader says where you are — the text,
  the section, the sentence across the middle of the window or the one you last tapped a
  word in — and says it again as you move, so the drawer shows the sentence above the
  box, sends it with every line, and offers one press that asks what it means. A word's
  card still answers two turns in place, and "Continue in chat" now goes on in the
  drawer beside the text. The conversation there is in Hebrew at your level, as it is
  everywhere, and so is a word's card now: a note of where you are decides what the
  answer is about, never its language, and the card draws the answer in the
  conversation's shape, the Hebrew with its English under it. Off a disk the reader
  carries nothing to talk to, and the page still fetches nothing by itself.
- Learn is the reader, the size of the screen (2026-09-11: "less empty space and more
  filled up by the reader — especially on larger screens; on mobile the reader can take
  up the whole screen"). The sheet runs the width of the window under one head row —
  Continue at the start, your count of words at the end — and its window is the height
  of the screen under it; the shelf keeps its reading width below. On a phone the sheet
  comes first, edge to edge, the height of the screen between the two bars, with the
  count and the shelf under it. On the front page the reader's kept list stays out of
  the sheet. The sheet's title, what it is, how far you are and Open stand at its head,
  above the text, so the first thing on the page says what you are looking at. Decided
  with David the same day: the page opens with a greeting and today — the time of day
  and your name, the date and the week's portion where the box carries it — with your
  count of words on the same line; beside them one control of doors, one press each:
  Continue reading, Suggested — a text that fits your level and interests, picked as
  the conversation's "Something to read" is but with no conversation (`GET /suggest`,
  leaning towards the registers you already read; a suggestion you have finished makes
  way for the next) — and Subscriptions, one door however many you follow, with a menu
  under it that marks a newest instalment you have not seen and names the one in the
  sheet. The
  conversation stays the pill at the foot of the page, and whatever it offers opens in
  the sheet. The date carries the Hebrew date in parentheses. For a new reader the
  count's place says what to do here. The weekly is named Weekly News Digest wherever a
  series is named.
- The sheet on Learn draws the reader whole (2026-09-11, live: a subscription there was
  "missing most of the reader features including translations and toggles"): the bar
  and the kept list are drawn in the sheet as on the reader's own page; what the front
  page still changes is that links stay in the frame and a visit counts at the first
  press. Open on a subscription goes to the reader, never to the series' own page. And
  Suggested is never simply missing: with no pick from the server, the catalogue's own
  next step is the suggestion.
- The reader's kept list scrolls as its own thing (2026-09-11): a thin bar at the
  panel's outer edge rather than a wide one drawn between the rows, and reaching the
  end no longer scrolls the text behind it.
- A conversation opened again keeps its cards (2026-09-11). The card a text was quoted
  on was drawn from the live stream only, so the drawer in a reader — reopened on every
  page — showed targum saying "press the card" over no card. Each answer now comes back
  with the cards it quoted, as the texts stand now, and a card for a page on the web
  links to it by the site's name. And nothing is "built" to you any more: a text is
  getting ready, and then it is ready, in the card, in the bell, and in what targum says.
- A command palette on every page (2026-09-11): ⌘K, or the search in the bar, finds a
  place, a text on your shelf or in the catalogue, or a conversation, and Enter goes
  there — a conversation opens in the drawer.
- The sheet on Learn says how long is left, "about 12 min left", from the sections the
  reader records as finished and the text's own length, and draws it as a line along
  its foot (2026-09-11).

### Changed
- The verb follows the medium. Buttons and labels assumed a reader was there to read, and
  many come to listen and to watch. A door on Learn now says Continue reading, Continue
  listening or Continue watching by what it leads to, its lead button says Read, Listen or
  Watch, the hint over the sheet says the same, and a Library row's build button says
  Start reading, listening or watching. "Listening" is for a text that began as a
  recording — a talk, an imported podcast — and not for a text with a reading attached,
  which is most of the shelf. Where no row is known yet the word is neutral: Add asks
  "What would you like to learn from?" and its button says "Open it". The ledger counts
  "days on targum" and "words learned on targum". "{share}% read" is "{share}% through",
  "Recently read" is "Recently opened", "Read next" is "Up next", and three sentences that
  said "the shelf" say what they mean. English and Russian moved together, and a new test
  fails when an English sentence changes and its translation does not: `strings/from/`
  records which English each translation was made from, and
  `scripts/stamp_strings.py` stamps it again (design.md §6, targum-internal#337).
- For a new reader, the conversation's first exchange goes on (2026-09-11): once words
  are marked, targum's next turn is a text at that level, asked for without a model
  turn, so a text is two presses away without leaving the page. The count line on Learn
  waits for ten known words before it counts; until then it says what to do.
- The bell keeps what you put away, says when the month's hours are three quarters gone,
  and says when targum answered a conversation while you were away — the list now
  carries when you last opened each and when targum last answered (2026-09-11). Follow
  on a subscription is a switch; the Library's filters fold behind one word, its search
  staying out; the last small-capital labels on the desk are in normal case.
- The desk grows up, phase 1 of five (2026-09-11: "the whole design feels clunky, like
  it's from 2016 not 2026"). Corners on the desk's own scale — 8 controls, 12 rows and
  fields, 16 cards, 24 sheets — named by token; depth in three shadow tiers instead of a
  line around every box, a hairline only where two same-tone surfaces meet; the bar is
  glass, sticky where it is one row, with the places as tint pills; buttons are three
  kinds — filled, tonal, ghost — and all pills; fields are wells with no line and a ring
  on focus; one motion curve, 240ms in and 160ms out, and a press that gives. design.md
  §8 says its radii are the reader's and §13 carries the desk's; `test_brand.py` admits
  the new corners. Every chrome page changes a little at once and nothing changes shape.
  The plan: https://claude.ai/code/artifact/8408e102-f2aa-4ac3-9da7-3cb2a91ab186.
- Phase 2: Learn and the drawer. The shelf loses its column heads and its fold, its
  covers take a row's corners, See all is a ghost pill, and the one label on the page is
  a heading in normal case; in the drawer your turns are tint and targum's are on the
  card, the box sits on its own strip at the foot, and the drawer settles out the way it
  came in (2026-09-11).
- Phase 3: rows, not tables. Your Words and the may-already-know checklist are rows —
  the word large in its face, what is known of it on a second line, the column heads
  gone — with the checklist's two presses on a glass strip that stays at the foot while
  the list scrolls; the Library's sort head is a row of pills and every text a row with
  a row's corners (2026-09-11).
- Phase 4: the phone. The three places are a bar at the foot of the window, a glyph
  over each word, on glass; the top bar keeps the mark, the bell and your picture; Talk
  to targum is a round button above the bar; the account's and the bell's panels come up
  as sheets from the foot (2026-09-11).
- Phase 5: the reader's own chrome — its bar on glass with pill controls, the word card,
  the keys and the picker on the card's corners and the floating tier, its phone sheets
  on the sheet's corners; the page's lines, faces and brown untouched (2026-09-11).
- Talk to targum is a pill at the foot of every page, and Learn is the reader's own
  highlight (2026-09-11: "'talk to targum' can be in the sticky CTA on every page that
  opens up for you — doesn't actually have to live on any page. Learn page can literally
  just be a highlight of the reader"). The pill opens the conversation as a drawer — from
  the edge on a laptop, a sheet from the foot on a phone — holding the conversation page
  framed; nothing is loaded until it is opened, Escape and the scrim close it, and it is
  open again on the next page since the conversation is not over. A text it offers opens
  in the sheet on Learn and on the reader's own page anywhere else. Learn keeps the
  count, the sheet across the row at a reading height, and the shelf; Hide and Expand
  went with the card they worked on.
- Learn is the room you learn in, not a lobby (2026-09-11: "it's no longer a home page
  but an actual page for learning"). The Read row, the word and phrase panels and the
  may-already-know checklist left it; the sheet, the conversation and the shelf stay.
  One sheet for both Hebrews: the track opened most recently takes it. Your Words is a
  page behind the account — the words, the checklist, the phrases — linked from the
  account panel on every page. The checklist is the conversation's first exchange for
  a reader with a ledger of nothing and no conversation, and lives on Your Words after.
  The Library carries Your subscriptions above the list: the weekly, the weekly portion
  and each learning cycle, each with where it is this week, Follow and Open;
  `GET /series` answers where each is. A followed series' newest instalment takes the
  sheet on Learn the first time it is seen and is said in the bell on every page.
  Following is kept on the account (`/account/follows`) as well as in the browser, so
  the row is the same wherever you sign in — and the server mails followers when an
  instalment lands, once, with a one-press door out (`/series/stop`); the weekly keeps
  its own mailout. The row is a panel on the profile, behind the account, and the
  account panel links to it: the main pages stay as simple as they can.
- The reader on the front page works, and the conversation can be put away. The sheet
  is the reader itself, framed: a press in it marks a word, turns a page, opens a
  chapter; its own links stay in the frame and every other link opens the page; a visit
  is counted at the first press, not at being shown. Hide on the conversation's card,
  or Expand on the sheet, puts the conversation away — the sheet takes the row and grows
  to a reading height — and a pill fixed at the foot of the window brings it back; the
  choice is remembered in the browser. A text the conversation offers opens in the
  sheet first, beside the conversation, and Open goes to its own page. In the frame,
  New is drawn only once a conversation is open, and the empty-state line is not drawn
  at all (2026-09-11: "the 'new' button is completely pointless, and you turned this
  back into a wall of text").
- Notifications are a bell in the bar. What is building and what is ready used to be one
  pill fixed at the foot of the window showing one build at a time; now the bell in the
  top corner carries a count, and the panel under it lists every build, newest first,
  each with Open when it is ready and its own ×. Putting a live build away still asks to
  be told by email where the server can (2026-09-11).
- Two lines said the active way (2026-09-11): the box's placeholder is "Write in Hebrew
  or English", and a text's fit is "You know 62% of its words" on the sheet and in the
  chat's suggestions.
- Words you may already know gathers pages until at least ten words remain: a page of
  fifty set against a ledger that held most of it came down to one or two words at a
  time (2026-09-11).
- Words you may already know works with checkboxes: one on every row, one at the head
  that checks the page, and "Mark checked as known" writes the checked words as known
  and passes over the rest, since they were looked at and left; "None of these" passes
  the page. It used to be all or nothing — "I know all of these" or "Not these"
  (2026-09-11).
- The chrome has a system of its own, the desk (design.md §13), and the front page is
  the first page on it: every chrome page stands on the desk in the chrome's own face,
  Source Sans 3, carried in the page like the Hebrew faces; the header is the ink bar;
  cards lift off the ground; teal marks every control; and the text to carry on with is
  drawn as a sheet lying on the desk — the reader itself, framed as a picture of itself
  at the place it was left, with its title and one press under it — beside the
  conversation, which is the conversation page itself framed without its bar
  (`/chat?embed=1`): what is typed there is answered there, and a text it opens opens
  in the page that holds the frame. A framed reader is told it is a picture
  (`?preview=1`) and counts nothing as read; both frames may be framed by this origin
  and by nothing else. The reader never loads the face. `test_brand.py` widens its palette and type
  scale by exactly what §13 names. The desk holds from a small phone to a television:
  the rem scales from 16px to 22px with the screen, a chip cuts a long title short
  rather than running out of its card, Read is one row of cards, the weekly is a row
  that reads, and the building pill takes the foot of a narrow window; checked in the
  browser at 320, 375, 430, 768, 1024, 1440 and 2560 wide (2026-09-11).
- The front page is in named parts, and a line typed there is answered in place. Under
  the count, Talk to targum with one sentence saying what it is, the box, the things
  most readers ask as verbs, and the thread opening under them — the conversation page's
  own script, run on Learn — then Your conversations, then Read with its own sentence.
  The parts step down with space rather than rules; `box.js` is gone (2026-09-11, from
  looking at the page: "nothing is labeled", "I can't really tell that it's a chat", "I
  should not be sent to a new page").
- The conversation page is the viewport: the thread scrolls inside itself and the box
  stays in view however long the conversation, where it sat under a thread of unbounded
  height and scrolled away with it. Who said a turn is told by where it stands — the
  reader's lines set in from the start, targum's from the end, the same ink — and the
  name rides as the turn's label for a screen reader, where a word stood over every turn.
  An answer arrives by appending its tail rather than redrawing the line on every piece,
  with a caret while it writes; the thread follows the newest line only while the reader
  was at the bottom; a new turn fades in over 200ms and not at all for a reader who asked
  for no motion (targum-internal#247, from the notes of 2026-09-10).
- Hear a silent text. On a Hebrew section with no recording, This text carries one
  door, "Hear this section", with what it costs in the reader's own hours beside it.
  The press claims the estimate in the hours a recording comes out of, the section is
  read aloud one line at a time so the spans are exact without an aligner, the lines
  land as one part in the audio manifest beside the reader, and the page is rendered
  again with the audio in it and every per-line control; settled to the clip's own
  seconds. Drawn only while the voice has a price beside `transcribe.PRICES`, which it
  does not yet: an unpriced voice is not for sale (targum-internal#246, from the notes
  of 2026-09-10).
- Words you may already know, on Learn under Your Words: the commonest words of modern
  Hebrew that are not on the ledger, fifty at a time, with the meaning the glossary
  already holds, and "I know all of these" — every mark an ordinary known word, so the
  count rises because it did, and never a level a reader could claim. "Not these" passes
  a page over. `/words/common` serves the list and buys nothing; a reader with no ledger
  who says they read Hebrew is told once where it is (targum-internal#245, from the
  notes of 2026-09-10).
- How much of a text a reader already has is estimated before it is quoted: the
  ledger's known forms and the commonest words against the text's tokens, a prefix or
  two allowed, no lemmatizer. The card says it in words — "You know about 7 words in
  10 here" — `describe_source` and every quote carry the number, the library search
  applies the reader's own ceiling when the model names none, and the prompt names the
  target: 0.8 for a first read, 0.65 for something harder (targum-internal#244, from
  the notes of 2026-09-10).
- The line under each Hebrew line in a conversation is in the language the account
  reads into, where it was English by name: the contract names it, the record's
  meanings are looked up in it, and the read-back builds into it. A first visit from a
  browser in Russian is asked once, in Russian, whether the lines should be in it;
  never guessed silently (targum-internal#243, from the notes of 2026-09-10).
- The recast says when it corrected. A recast that differs from what the reader wrote
  in Hebrew is labelled corrected, the words that changed carry a mark, and one folded
  line under it — the model's `~ ` line, what changed and the rule, one sentence — opens
  on a tap; open for a reader with no words yet. A line that was right, or written in
  English, gets nothing, the body still does not lecture, and a text written from the
  conversation carries no `~ ` line (targum-internal#242, from the notes of
  2026-09-10).
- The English under each Hebrew line in a conversation is folded, and a tap on the pair
  opens it — the gesture that opens a word's gloss — with one Show English at the head
  of the thread for all of it, remembered. The recast stays open, and a reader with no
  known words sees it all open. "I would just ignore the Hebrew and read the English"
  (targum-internal#241, from the notes of 2026-09-10).
- The things most readers ask are buttons under the box on Learn and in the empty state
  of the conversation page: "Something to read", "Continue *title*", "Use my new
  words", "What do I know", "News today", "A word I am stuck on" — each drawn from the
  record and standing only where its condition holds, never under an answer. A press is
  Send with a fixed line; the first is answered by the server from the library with no
  model turn and no spend, as the same card the model's own quote hands the page, with
  "Another" under it (targum-internal#240, from the notes of 2026-09-10; design.md §12
  records that this reverses a cut of 2026-09-06).
- A way back to a conversation. A row writes the conversation into the address, and the
  address opens what it names, so a conversation can be linked to and the back button
  goes to the one before; each row says when it was last opened. On a phone the list is
  a sheet behind a pill at the top of the page, where it used to sit under the whole
  thread. Learn carries the last three under the box with the door to all of them. The
  list is a page of fifty with More at its foot, where it used to be every conversation
  ever in one answer (targum-internal#238, from the notes of 2026-09-10; design.md §12
  records that this reverses a cut of 2026-09-06).
- The chat's prompt is cached whole. The block after the breakpoint — the reader's
  words, the bring-back slice, the exemplars — was drawn afresh every turn, and since
  the history comes after it, the whole conversation fell out of the cache every turn;
  one conversation now sees one draw, seeded by its id, and the next conversation the
  next. The ledger block and the last message carry breakpoints of their own, so a turn
  reads the history back rather than paying for it again, and what the cache read and
  wrote is counted and priced on the receipt, where until now it was read past
  (targum-internal#239, from the notes of 2026-09-10).
- The month's hours are off the conversation page, where they stood in the side column
  on every visit. The count is under the ledger on Your Progress, with the day the
  month turns, and in the account panel on every page; the box says it only once three
  quarters are used, so the cap is not the first anybody hears of it. `/account/me`
  carries the hours, reckoned in the one place `/chat/list` already reckoned them
  (targum-internal#237, from the notes of 2026-09-10).
- A reply is at most three Hebrew sentences, the recast left out; one sentence and the
  door when a text is handed over; six lines at most when the answer is a list. "A few
  Hebrew sentences" was a median of 36 words over five lines, ten with their English, on
  the conversations stored so far, and the notes of 2026-09-10 called it too much to
  read. `scripts/measure_reply_length.py` counts what real readers got, and
  `scripts/eval_grading.py` now records `hebrew_words_median`, with a floor of 25 in
  `evals/floors.json` (targum-internal#236).
- The box is one row: the `+`, the field, Speak and Send side by side, on a phone as on
  a desk, where the three buttons used to sit on a row under the field. Speak, Send and
  Hear are drawn rather than written — a microphone, an arrow, a loudspeaker, from one
  sprite to §7 — with the word kept as each control's label, so nothing a screen reader
  says has changed; the `+` stays typed. The field grows with what is typed and shrinks
  back when the line is sent (targum-internal#235, from the notes of 2026-09-10).
- The chat's web search looks at the whole web, six searches a turn instead of three.
  Until now it was held to the known Hebrew sites, with a card a reader pressed to widen
  one turn: a list the model could not see made a gap in it look like an answer, and the
  card cost a second turn every time the list failed. A search is a cent inside the
  turn's own meter; what keeps the answers Hebrew is the Hebrew the model searches in
  and the Hebrew share `describe_source` counts before anything is offered. Gone with
  it: `offer_wider_search`, the `wider` flag through `/chat/say`, the "wider" stream
  event and the Look wider card. `sources.allowed_domains()` stays as the record of
  which sites are known and measured.
- A verb's meaning is filed apart from a noun spelled like it. DICTA names many verbs by
  their present participle, and off the Tanakh a participle is a noun as often as not:
  מְשַׁנּוֹת, "are changing", was filed under משנה with מִשְׁנָה and its card read
  "doctrine; teachings" beside the verb's own grammar line. `Token.glossed_as` now files
  every verb under its lemma with " (verb)" after it, the way a pointed headword files a
  contested biblical spelling; the lemma stays the word's identity for marks and bands.
  Computed rather than stored, so a plain `targum rebuild` re-keys every page without
  re-annotating; the changed keys are bare until re-bought (about $4.20 for every verb
  through `rebuild --gloss`, or a word at a time on tap). `targum correct` takes
  `'משנה (verb)'` for the verb. The card's question to the chat now carries what the card
  shows, and the note says the model cannot change it.
- The Hebrew contract no longer says "give the reader something to answer". With "a reply
  may also simply end" one bullet earlier and the bring-back words in the same block, the
  model was ending every reply in homework built from those words.
- Web search rides along unless the box says not (`TARGUM_WEB_SEARCH=0`). It was off
  unless asked for, and a reader who asked for something to read online was told the
  box could not look. Three searches a turn at most, each counted, inside the same
  rails every turn is; what it may look at is still the publishers' hosts and the
  public ones.
- Natural Hebrew before the list. The contract asked the chat to stay inside the
  reader's words with at most one word outside per sentence, and a wall like that bends
  sentences. It now says: prefer the reader's words wherever a natural sentence allows,
  never bend a sentence to avoid a word, and bring new words in on purpose — two or
  three a reply, chosen to be met again, each with its English, and used again a few
  lines later. Comprehensible, natural, one step at a time; the outside share is still
  recorded on every turn for the eval.
- A first day has no ledger. A reader who has marked nothing is not written to at 800
  common words and left there: the chat is told to keep to the commonest of them, keep
  every sentence short, ask what they have read in Hebrew so far — never what level
  they are — and offer one short text to start with, because words are marked while
  reading and that is how a ledger begins. And the foot of the record no longer tells
  them they knew 0% of it: it says how many words there were and that none are marked
  yet.
- The Hebrew the chat writes is written as Hebrew. The recast of a reader's English
  was carrying their grammar mistakes and their English word order into the line of
  record, and the model's own lines read as translated English ("זה ישר" for
  "plainly"). The contract now says the recast is what they meant, said the way a
  Hebrew speaker says it, and that its own lines are written in Hebrew first, the
  English under each being the English for the Hebrew and not the sentence it started
  from.
- The chat knows the ladder a reader may name. Asked for "a bet plus level", it did not
  know what that was: the rungs and what each is reckoned to want are written into the
  prompt from the one table `level.py` keeps, and it is still told never to hand the
  reader's own rung back.
- A sense bought bare is grounded by the first sentence that meets it. The catalogue holds
  glosses bought without a sentence, and asking again without one returns the same answer:
  the held gloss for עם is "people; nation", with the preposition not there at all. So the
  catalogue is not re-glossed in bulk. A bare sense is re-bought once, the first time a
  reader taps the word in a sentence, and the grounded answer stands for every reader
  after. `Sense` and the cache record carry `grounded`, absent on everything glossed
  before today, which is the point; a provider failure on the re-buy hands back the held
  sense rather than a 502. The ceiling is what a bulk pass would have cost, but the spend
  is on demand and only for words readers actually meet (targum-internal#42).
- The box installs the CPU build of torch. PyPI's Linux wheel is the CUDA build and
  brought 4.9 GB of driver libraries to a machine with no GPU; the deploy now resolves
  against PyTorch's CPU index beside PyPI, which changes torch alone and drops the
  nvidia, cuda and triton packages, every other package staying where PyPI put it
  (targum-internal#93).
- The export carries who a reader said they are. `/account/export` already looped every
  kind the account syncs — words, meanings, phrases, texts and the days somebody read on,
  which is what the progress page is made of — but the name typed on the profile page and
  the languages chosen there are not a synced kind, and left with nobody. Both are in the
  file now. The nightly copy needed nothing: it takes the database whole, so a table added
  tomorrow is in it tomorrow, and a restore is now run end to end in the tests and judged
  by the same export rather than by a count of words (targum-internal#17).
- `targum repair` can take a space out. The spacing repair once cut after every final
  letter it found, so a scanned text with ו read as ן came apart into a lone final letter
  and the rest of its word, and a text built then still carried the space with no way to
  close it. A lone final letter is not a word, so the space in front of the word it belongs
  to comes out again — the one join the text itself can prove, and a letter an
  abbreviation's gershayim touches is never it. Every built text was scanned and all 611
  are clean (targum-internal#86).

### Fixed
- A build request can no longer have the server read a file off its own disk. The Add
  page's door took `source` and `translations` as given, and the ingester reads a path
  as readily as a link, so a signed-in request naming a path got that file back as a
  text or as its translation; the door's own docstring said nothing could. `source` must
  now be a link or a fetcher's identifier (`ingest.fetchable`), or a source the catalogue
  names; `translations` is taken only where the catalogue holds that list for that text,
  which is all the Library's button ever sends. The chat's quote tool shares the rule and
  stops letting a path with a colon in it through. Carrying `translations` no longer lets
  a `from` targum does not read past the check either. Links were already safe: the URL
  ingester refuses private addresses on every hop.
- Speech has a price, and every money ceiling sees it. The voice was counted in seconds
  and charged nothing, so a spoken reply and a read-aloud section were claimed at $0,
  and the box's day, the account's and the chat's — all sums of claims — could not see
  a cent of it; an admin had no bound at all. `speech.PRICES` holds Gemini 3.1 Flash
  TTS at $0.03 a minute ($20 per million audio tokens at 25 a second), in its own table
  because `transcribe.PRICES`'s dearest row is the fallback quote for a recording. A
  spoken reply is claimed at that rate for its words and settled to the clip, onto the
  conversation's total too. Pricing it opens "Hear this section", as #246 decided, and
  that door had two faults waiting behind it: the press claimed before its job was
  written down, so the reservation updated no row and went nowhere, and two presses made
  the section twice. The job is written first now, and a second press joins the first.
  A voice that stops part-way settles the lines it already said instead of releasing
  them, and a spoken reply that fails in any way gives its claim back. A test fails when
  a model targum spends on has no price, so this cannot recur quietly.
- Stanza loads no model unless its training data has been checked, and none has.
  `LICENSING.md` said Stanza kept "every other language it served" once Hebrew left it,
  on the assumption that only Hebrew's treebank was NonCommercial. It was not: English's
  default model includes GUM and Russian's is SynTagRus, both CC BY-NC-SA, and every
  build carrying a published English prose translation split that English with it
  before lining it up. `segment/stanza_segmenter.AUDITED` lists the language and exact
  build that may load, and is empty; the download, the tokenizer and the lemmatizer all
  refuse anything else before importing Stanza, including `hbo`, which slipped past a
  check on the literal `he`. Sentences in a script with capitals are drawn by rule
  (`segment/cased.py`: the Hebrew rules taught case and a short abbreviation list per
  language), and Yiddish and Aramaic paragraphs, which used to fail the build at Stanza,
  are split by the Hebrew rules. A matched alignment is keyed on what split the
  translation, so the eleven affected alignments line up again for nothing rather than
  pointing at segment ids that no longer exist. Hebrew splits exactly as before, no
  annotator name moves, and no translation is bought. `LICENSING.md` states the rule now:
  a model trained on NonCommercial or ShareAlike data is not used.
- Buying a recording's second part, or a book's next chapter, no longer rebuilds the
  reader without a word to tap. Every reader is built through one place, and that place
  read `words` off the door's options and took silence for no; the part and chapter
  doors write their own options and never said it, so the reader came back with no
  marks — the first part's included — and the job said `done`. The chat's two doors had
  been through this once and were mended one at a time. Now a door that says nothing
  gets words, since nothing anywhere asks for a reader without them, and a door that
  says `words: false` out loud is still heard.
- A door the model spelled with the wrong final letter opens. Told to copy a reader's
  path exactly as the tool returned it, the model wrote בסטארטאף for the folder
  בסטארטאפ, twice in one conversation, and the door answered "not found". A name that
  differs from a folder's only in its final letters is sent on to that folder, query and
  all, where exactly one folder matches.
- A mark that moved to a word's new name when the annotator changed (targum-internal#141)
  now reaches the account. The move stamped nothing and buried nothing, so the sync never
  sent the record under its new name and the account kept the old one: a second device
  brought the orphan back on its next pull, and the chat's ledger, which is read from
  the account, never learned what the word is now called. The moved record is now
  touched at the move and the name it left is a tombstone — the two facts a reader's own
  delete leaves — and a name this browser has buried more recently than the account's
  record of it stays buried on the way in, the same newer-edit-stands rule the account
  applies on a push.
- On a machine somebody runs themselves the chat's dollar-a-day rail is off: the reader
  is the operator, whose `--budget` is the ceiling. An evening of testing was told to
  come back tomorrow by its own laptop. Hosted, the rail stands.
- A browser that moved on before a JSON answer landed printed a traceback in the
  terminal for every dropped request; the stream already treated a broken pipe as the
  reader leaving, and the plain answers do now too.
- A conversation titled with a long first line pushed the rail out under the thread,
  where every title was cut off behind the raised paper: a grid item's minimum width is
  its content unless told otherwise. Measured in Chromium now.
- Sonnet 5 was priced at 3/15 per million tokens in `PRICES`, which is Sonnet 4.6's rate;
  it is 2/10. `Usage.cost()` reads that table to settle the ledger, so every hosted build
  since the model arrived was recorded at half again what it cost, and `targum usage`
  could not have agreed with the bill.
- yt-dlp no longer speaks to readers in its own voice, and where YouTube is fetched from
  is a setting rather than an assumption. A reader who pasted a YouTube address on the box
  was shown, in the red box on /add, a paragraph naming `--cookies-from-browser` and two
  GitHub wiki pages: `video/youtube.py` carried the binary's last stderr line verbatim
  into `job.error`, which is right for "Private video." and wrong for a note addressed to
  whoever runs the binary. The line is now carried only where it is a fact about the
  video; a sentence holding a flag or a URL is dropped for targum's own, which names the
  door that does open — a video file uploads. `fetch` and `describe` had two copies of
  that logic and only one was ever read; they share one now.
  Behind it, why the fetch failed at all. Measured on the box: the same video answered on
  a laptop and came back "Sign in to confirm you're not a bot" on targum.page, and so did
  a 2005 video with no restrictions of any kind, which is the control that rules out
  anything about the video. Every player client failed, `-4` and `-6` both failed, and
  neither a JavaScript runtime nor a proof-of-origin minter helped: YouTube has flagged
  the Hetzner range, and nothing that runs *on* the box answers that. So the fetch has to
  leave from somewhere else, and `TARGUM_YTDLP_PROXY` is where that somewhere is named —
  a tunnel to a machine YouTube already trusts, or a residential proxy. Not a cookie file,
  which would be a Google session living on the box, refreshed by hand, fetching on behalf
  of strangers, with a ban as the failure mode; a proxy is an egress and carries no
  account. `targum preflight` now says which half is missing, warns a hosted box that has
  no egress at all, and names a dead one by host and port only, because a proxy is bought
  with a password in its URL and that line is printed by the deploy and again into the
  journal. `deploy/provision.sh` installs deno, the minter (`bgutil-pot.service`) and the
  yt-dlp plugin into the tool environment that actually runs; `deploy/nftables-targum.conf`
  closes port 4416 to everything but the loopback, because the minter binds every
  interface at 1.3.2 whatever its README says, and the box ran no firewall at all.
- On a phone, a word's card no longer moves the page (targum-internal#155). The card was
  an occupant of the band at the foot, and the pages were cut again around it: a tap on a
  word turned 60 pages into 80 with the card up and 60 again as it closed, so one look at
  one meaning moved the screen twice, and the words in front of the reader changed each
  time. A word's card and a phrase's chip are now overlays — drawn over the page, the
  strip, the arrows and the sheet, and measured by nothing — and the page holds still
  until it is turned. `design.md` §12 records the departure. Two more that went with it:
  the first letter of a custom meaning used to open the sheet, which on a phone put the
  card and its field away mid-word (writing a meaning is what keeps a word for the first
  time, and the first word kept opened the sheet); and a keyboard that shrinks the window
  used to lay the pages out again for the sliver above it. The sheet now waits while a
  card is up, a height-only resize while a card's field has the focus is left alone, and
  on a browser that shrinks only the visual viewport for its keyboard — iOS Safari,
  Chrome on Android — the card is lifted to the visible foot of the window.
- `targum rebuild --gloss` buys the meanings the cache lacks, and the deploy passes it.
  A rebuild filled glossaries from the cache and never bought, which was right until an
  annotator started filing words under keys nobody had paid for: `oshb/2` reached the box
  and 92 of the 200 rows on the first page of Judges — היה, אמר, מות — opened on "look
  it up". Free stays the default; `--gloss` says what it bought and about what it cost,
  and buys bare, so the first tap on each word grounds it the way a build's do.
- Every count of words is the same count. "You know 1,285 Hebrew words" on Learn and
  "1,439 words marked known" on Your Progress were the same account at the same moment,
  and the gap was names and numbers: a name marked known has been left out of what
  counts as vocabulary since 2026-08-28, because knowing that אחשורוש is a king is not
  knowing a word of Hebrew, but the rule had been applied one figure at a time. The
  milestones, the ulpan ladder and Learn's headline filtered for themselves; the ledger,
  the status bar, the growth line and the day strip drew from the shared list and took
  the names. The rule now lives in the one place every chart reads from, so words
  saved, words learned and the bar of where they are move with words marked known, and
  no two figures on the page can disagree again.
- A word that shares its spelling with another is glossed as itself. הָאֵלֶּה in
  Deuteronomy 30:1 showed "curse; oath, pl. אלות": the scripture path takes the lemma
  from the Strong's headword and strips the points, so אֵלֶּה (these) and אָלָה (a curse)
  were both filed under אלה, one cache entry between them — and the first tap on one of
  Nitzavim's five curses grounded that sense for good, onto every "these" in the Tanakh.
  A token now carries its pointed headword where the lexicon has more than one word
  spelled that way (1,160 of 6,242 bare spellings; 2,851 headwords between them), and
  that is what its meaning is bought and filed under, on the page and at the tap. The
  lemma stays bare: it is the word's identity across every text — marks, counts, the
  list — and a reader's marks on אלה still cover both. Only the shared spellings are
  bought again, one gloss each, and only as texts are rebuilt. The annotator is renamed
  `oshb/2`, so every text is re-annotated on the next `rebuild --words`; that is the
  two-hour operation the docs describe and should ride with the segmenter change rather
  than after it. The pinned "curse; oath" under bare `אלה` on the live box is untouched
  by this and has to be dropped by hand.
- The first word of Nitzavim is no longer "modern · not in the Tanakh". The band table
  behind the Tanakh levels and the register line was counted with Stanza on 2026-08-24
  and never recounted after the hand-tagged lookup replaced Stanza on scripture and DICTA
  replaced it everywhere else; both lookups match the lemma exactly, so every headword
  spelled another way — half of them, `אתה`, `אני` and `הם` among them — was "not in the
  Tanakh", and a verse DICTA read wrote `ניצב` where the table had `נצב`. The table is
  now the Tanakh counted twice, through the two things that read it: once under the
  tagging's headwords, through the same function the lookup files words under, and once
  under DICTA's lemmas, since the tagging says `בוא` where DICTA says `הביא` and no rule
  folds one onto the other — merged on the easier band (`scripts/count_tanakh.py`). A
  name either reader can file a word under is a name the table has. It is also the
  first table with no Stanza in its ancestry. On a text that is the Tanakh the register
  line now never says a word is not in it — a miss there is a spelling the count did
  not see, not a fact about scripture. `tanakh/2` and `register/2`, renamed together so
  the shelf is re-annotated once. `targum preflight` says whether the tagging is on
  disk where the service can see it, because a box without it reads every verse with a
  model and used to say so nowhere (targum-internal#156).
- The `file://` canary watches the mechanism that was actually fixed. It wrote with
  `localStorage.setItem` and read back with `localStorage.getItem`, the one path
  `durable.js` does not repair, so it was watching a fault that was never going to clear
  while promising its `xfail` marker would come off when the fix landed. It now goes
  through the reader's own path and polls durable.js's IndexedDB shelf for `targum:place`:
  `localStorage` answering yes only proves `targumKeep` ran, which on `file://` is
  precisely the worthless answer, while the shelf answering yes proves the write
  committed. The marker is off (targum-internal#137).
- A verse link into a portion lands on the aliyah that holds the verse. A book is one
  chapter per file, so sending `index.html#16:20` on to the file that holds chapter 16 was
  exact; a portion's files are aliyot, and every one of the 71 built portions has a
  chapter running across two or more of them, so the same link opened on the first file
  of the chapter whether or not the verse was in it, and nothing scrolled. Each contents
  row now carries the first and last verse its file holds, and a verse takes the file
  whose range has it; a chapter alone, or a verse no file holds, still takes the
  chapter's first file rather than nothing (targum-internal#142).

### Fixed
- A word is a word of its language. An English name, a clock time or an emoji inside a
  Hebrew line came back a word: tappable, counted against "N of M known", and "Hannah"
  filed in the ledger as extremely hard, from a community notice photographed off a
  phone. A token with no letter of its block's script is now read past, in the reader
  and in the conversation's record alike. This is the annotator's `languages/3`, so
  every text on the shelf is re-annotated at the next rebuild — free of spend, not of
  time (see CLAUDE.md on renames).
- A word after an emoji is marked where the browser counts. Python counts a calendar
  glyph as one character and JavaScript as two, so every span after one landed a unit
  short: half of שחרית marked, the other half of the mark on the time beside it. Every
  offset that ships to a page now goes through `js_span`.

### Removed
- Dark mode, on every page. targum has one look, and it is light: the second palette, the
  switch in the bar, in the account's sheet and on the public pages, and the script that
  stamped the choice are gone, and a browser that prefers dark gets the same page as any
  other. The front door had been light-only since 2026-09-16; this is the rest. An
  inverted ink block, a film's letterbox and the favicon's own switch for a dark tab
  strip are not dark mode and stay. Readers built before this still carry the old theme
  until the shelf is rendered again (design.md §12, targum-internal#333).

## [0.2.0.0] - 2026-09-01

### Added
- The Torah can be read by portion, not only by chapter. The fifty-four weekly readings
  are one ordered collection on the shelf — פרשות השבוע, בראשית to וזאת הברכה, in the
  order of the year — beside the five books, which stay exactly as they were: two doors
  onto the same text. `targum parasha entries` emits the collection with the portions and
  `--write` merges it, rewriting the member list and keeping a blurb somebody edited;
  `deploy/ship-parasha.sh` runs the merge and carries the catalogue, so the live shelf
  cannot fall out of step with the corpus again. A Torah book's contents page groups its
  chapters under the portion each falls in, with the portion's name linking to its own
  first verse — נח to Genesis 6:9, in the file that holds chapter 6 — and a chapter two
  portions share listed once, under the one it starts in. Every portion page carries the
  reading before it and the reading after it, wrapping from וזאת הברכה back to בראשית the
  way the year does. Read off the corpus index at build time, so a reader still fetches
  nothing, and a machine with no corpus built renders every page as it did before
  (targum-internal#145).
- A verse answers to its address. Every verse of a Tanakh targum carries its number in
  the margin, the way a printed edition sets it, and its row is `#2:1` — chapter and
  verse, which is how every learner of a Biblical text locates a line — so a link to
  Ruth 2:1 opens on Ruth 2:1, in the scrolling reader and in pages alike. The number is a
  link to its own verse, so the address bar carries it and a reader can hand it on; the
  contents page sends `index.html#2:1` on to whichever file holds chapter 2, which is not
  always the second. Sefaria's `Ruth.2.1` is read as the same address (targum-internal#28).
- The Hebrew Bible is read rather than predicted. Scripture on the shelf takes its prefix
  divisions, dictionary forms and morphology from the Open Scriptures Hebrew Bible — hand
  tagging, CC BY 4.0, over a public domain text — instead of from a model guessing at a
  register it was not trained on. `targum models fetch scripture` brings it down; a verse
  the tagging cannot line up falls back to the annotator, as does everything that is not
  scripture. Measured over Ruth, 44% of dictionary forms change: `ויהי` was `ויה`, which is
  not a word, and is `היה`; `בניו` was `ניו` and is `בן`; `אשתו` was `איש` and is `אשה`.
- `targum licences` — what the corpus is under, and what may leave it. Each source already
  recorded a licence; what that licence *allows* is now computed rather than remembered,
  in `licensing.py`, and reported by standing: free, owed, closed, unknown. A source with
  nothing written down is unknown and never free, because an unchecked licence is not an
  absent one. Two verdicts the module exists to get right: ShareAlike is sellable and not
  keepable, and NonCommercial is the term that actually closes a door.
- `deploy/ship-daily.sh`, which carries the window to the box. Nightly, unlike the
  parasha's: the window rolls, and a stale box says "today" over the wrong day.
- `TARGUM_INDEX_DAILY`, a switch of its own for the learning cycles. They are not
  offered to search engines until it is set, and setting `TARGUM_INDEX_PARASHA` does not
  reach them: a corpus of fifty-four fixed readings and four pages that change nightly
  become ready to be found at different times.
- Daily learning, at four addresses: `/mishna-yomi`, `/nach-yomi`, `/tanakh-yomi` and
  `/tehillim`. Each shows what its cycle reads today, with the reading itself on the page
  — cut out of the texts already on the shelf, so the translation, the word cards and the
  vowels come with it and a day costs nothing. `targum daily build` rolls the window
  forward and is safe to run nightly from a cron.
- The cycles are data, not four modules: Hebcal answers for all thirteen in one call, and
  what differs between them is only how a reference names a place on the shelf. The nine
  it publishes that targum cannot serve are named on the page rather than left out —
  Daf Yomi and the Yerushalmi are a licence wall, not an oversight.
- The Tanakh is complete. Jeremiah, Ezekiel, Hosea, Joel, Amos, Micah, Nehemiah and both
  books of Chronicles, on the accented Hebrew beside JPS 1917, both public domain. Thirty
  books became thirty-nine, and Nach Yomi can walk all of them.
- Every text page says what it is about in JSON-LD, and calls itself a book rather than
  a website. Four hundred pages about four hundred books looked to a machine like four
  hundred pages. `author` is deliberately absent where the byline names a division rather
  than a person — `Ketuvim · Ruth` is not somebody — and what a text belongs to is said
  off the collections instead.
- Opening lines for two hundred and thirty texts, up from a hundred and four. Eighty-four
  of them had gone up with no Hebrew on their public page at all.
- The Mishnah, whole: all sixty-three tractates, 524 chapters, 4,187 mishnayot, in Torat
  Emet's pointed public-domain text beside Joshua Kulp's CC-BY English. Every tractate
  pairs by number at full confidence and not one mishnah is untranslated. Read as six
  sedarim on the shelf. Nothing was bought from a model.
- Collections: several texts the library meets as one row, opening where they stand.
  Three hundred and fifty-two rows is not a shelf anybody browses — the Mishneh Torah was
  thirteen rows of `הלכות …` and Berdichevsky thirty-nine stories. Nineteen of them now
  cover three hundred and thirty-three texts, and the list is thirty-six rows. It stays
  one list: a collection is built out of what survived the filters, sorts on its own
  totals beside the texts, and a search opens what it found. See design.md §12.
- Five registers instead of two, oldest to newest: Biblical, Rabbinic, Medieval, Revival,
  Modern. A hundred and fifty-nine entries filed "Modern" were written between 1853 and
  1930, and a reader who filtered for the Hebrew they could read was being handed Gnessin.
- Twenty-one texts of the Beit Midrash shelf, all read beside a translation somebody
  published and none of them costing a model anything: thirteen sections of the Mishneh
  Torah, the five ma'amarim of the Kuzari in Ibn Tibbon's Hebrew, and the weekday siddur
  in all three of its services. They are the first entries to carry the `judaica` tag,
  which until now was a vocabulary with nothing in it.
- Sefaria ingest reads anything shaped like chapters and verses, not only the Tanakh. A
  section of the Mishneh Torah is chapters of halakhot and pairs with its translation the
  same way a book of the Tanakh does — by number, at full confidence, for nothing.
- `siddur:` — a fetcher for the Sefaria indexes that are trees rather than books. The API
  refuses any reference above a leaf, so a service is walked and assembled from its
  hundred-odd leaves, and both languages are fetched for every one of them so that a leaf
  only one side has is dropped from both.
- Wikisource ingest drops the wiki's link rows from the top of a page as well as the
  bottom. A volume of a multi-part work opens with an edition picker and a contents row,
  and `drop_trailing_navigation` never saw them: they sit under no heading at all.
- A publisher's footnotes are dropped rather than glued into the sentence they annotate.
  Metsudah's siddur prints its commentary inline, and it is three times the words of the
  prayer.
- Video import: `targum build <youtube-url>` fetches a YouTube video with yt-dlp
  (CLI only, single videos, capped at 480p and 4 GB) and runs it through the same
  transcription and translation pipeline as audio. Direct links to video files and
  uploaded video files (mp4, m4v, mov, webm, mkv) work the same way.
- A video panel in the reader: off by default, toggled from the toolbar, showing the
  part's picture in a corner card while the existing player strip stays the transport.
  The picture is a sidecar file beside the reader — never inlined, never fetched from
  any network — and a reader folder copied without it degrades to the audio reader.
- The server streams video with Range requests, revalidation, and a response
  deadline; hosted uploads accept video suffixes (4 GB per file against one 8 GB
  media quota).
- Read-aloud recordings for prose: an external reading (a LibriVox book) can be
  attached to a text, force-aligned once, and cut into one part per section with
  word-level timings; the reader gets per-line playback and word clocks.
- The weekly landing page names the outlets its reporting cites, in their own marks.
- `/parasha`, the week's Torah portion, with the reading itself on the page. The corpus
  is fixed rather than generated: the fifty-four portions are cut once from the Tanakh
  already on the shelf — translation, word cards and vowels carried across with the
  segment ids, so a build costs nothing and fetches no text — and a calendar decides
  which one this Shabbat is. Doubled weeks, festival Shabbatot, and the weeks Israel and
  the diaspora read different portions are all handled, off Hebcal's leyning data.
- The seven aliyot are the reader's seven sections, so a portion opens on ראשון and the
  pager walks the reading the way it is called up. Every portion also has an address of
  its own and a place on the shelf, so a link to one keeps working after the week it was
  this week's.
- Scripture ships a third form of its text: the vowels with the chanting marks taken
  off, on its own two-position control (`a`, or the ⋯ menu). The te'amim are the point
  for somebody preparing to leyn and noise on top of the vowels for somebody still
  learning to read, and both are the same page. Every text without cantillation is
  untouched — two cells, one switch. See design.md §12.
- Chanted readings from PocketTorah (CC BY-SA, Ashkenazi trope), force-aligned so every
  verse knows its own second of the recording. A doubled week has no recording of its
  own, so its two halves are joined and re-cut where *that* week's aliyot actually fall.
- `--video/--no-video` on `targum build`, and a yt-dlp preflight check.
- `LICENSING.md`, naming the whole dependency supply chain and the two pieces of it
  that are licensed NonCommercial: the forced aligner behind the `speech-align` extra,
  and Stanza's Hebrew models through the treebank they are trained on. The AGPL
  promises a recipient commercial freedom that was not ours to grant over those two,
  so the file says so rather than letting somebody find out downstream.
- `CONTRIBUTING.md` and `DCO`. Contributions are signed off, and the sign-off also
  grants a sublicensing right — without it a single merged pull request would freeze
  the licence permanently, and the honest consequence of that would be accepting no
  outside contributions at all. Everything already published under the AGPL stays
  there, irrevocably, and the page says so.

### Changed
- Your Progress shades each day of the twelve-week strip by how much vocabulary was
  marked on it, on the same five-step ramp the about page's calendar uses. It was a
  two-state strip — read or not — which said you turned up and nothing else. Scaled to
  the busiest day on screen rather than to all time, so a first week of enthusiasm does
  not flatten every week after it; a day read with nothing marked keeps the faintest
  green rather than going grey.
- A biblical reader says, once in the keys panel, that its dictionary forms are the less
  reliable ones: the analyser is trained on modern unpointed Hebrew, so waw-consecutive,
  pausal and archaic forms are sometimes read wrongly on a card. It names the effect and
  not the library, and a modern text is not warned, because there it is not true enough
  to be worth the doubt.
- design.md §10 now bans ritual objects **in the identity** only. A page about the week's
  Torah portion is a content surface, and refusing it a picture of the thing it is about
  was the rule doing a job it was never written for. §12 records the new rule and its
  conditions, and the parasha hero is a photograph of a scroll beside the words.
- The serve policy's `media-src` gains `'self'` for the video sidecars
  (design.md §12, "a reader that carries moving pictures").
- Hosted pastes of YouTube links are refused by name with a pointer at the CLI.
- `pyproject.toml` states its licence as an SPDX string with `license-files`, which is
  the current PEP 639 spelling; the table form it used is deprecated.

### Fixed
- One spelling per word. A dictionary form is a vocabulary key, so two spellings of one
  word were two entries, two counts and two things to mark known. Ten pairs fold now —
  `כול` onto `כל`, `שמיים` onto `שמים`, `דויד` onto `דוד` — each one measured, checked
  against written frequency and confirmed by a reader. The pairs a reader refused are
  written down beside them, because `בת` and `בית` differ by one letter too, and so do
  `אחות` and `אחת`.
- A first build on a fresh box says what it is waiting for. Stanza fetches a few hundred
  megabytes the first time a language is used, and the page held whatever line it had
  printed before — "Finding each word's dictionary form…" — for the whole of it. A line
  that has not moved in four minutes reads as a hang, and the reader closes a tab on a
  build that was working. It now says which language model is being fetched, and that it
  happens once.
- A parasha asked for by name no longer titles itself "this week's parasha". Fifty-three
  of the fifty-four were saying it, in the tag a search engine weighs most, on a page
  whose argument is that every portion name is its own query. The headline had already
  been corrected; the title had not, and the test guarding the headline could not fail on
  it — the title is lower case where the headline is capitalised, and the apostrophe is
  written `&#39;`. A named portion now carries its chapter range instead, which differs
  for all fifty-four.
- The Wikisource fetcher drops a section the page labels as the vowel-less copy of a work
  it also carries pointed. The Bialik page was ingested as ten blocks — the poem, then a
  partial bare copy of it — and both were segmented, priced, translated, pointed and
  glossed, so the poem was paid for twice. It is four blocks now. Matched on the wiki's
  own heading rather than on the letters, because pointed Hebrew is written defectively
  and bare Hebrew is written full: the same line is צִפֹּרָה and ציפור, so the two copies
  never were the same string.
- Four of the fifty-four portions had no address. Matot, Masei, Nitzavim and Vayeilech
  were missing from the shelf, so `/parasha/nitzavim` was a 404 in the week Nitzavim is
  read. The corpus was enumerated from the same two-year window the pointer uses, and a
  pair doubled on both schedules across both years is never read on its own, so it was
  never cut. The corpus now walks nineteen years — the Metonic cycle, after which the
  calendar repeats — while the pointer still walks two. Fifty for years; fifty-four now.
- A failed video transcode no longer leaves a truncated file that later builds
  trust; a re-cut part is copied beside the reader atomically.
- Recording folder slugs hash only genuinely non-ASCII sources, so ASCII sources
  with underscores keep the folders they already have.
- `targum sources` and the "Supported:" hint shown when a file cannot be read both
  list the video formats. Neither had, since video import landed: the suffix set was
  added and its two consumers were not.
- The comment above the reader's range handling claimed If-Range was deliberately not
  honoured while the code fourteen lines below honoured it. The comment was written
  for an earlier design; the branch it guards now has tests for both halves.
- The video panel's close button gets the invisible 44px hit box on a touch screen
  that every comparable control already had. The panel floats over the text, so a tap
  that missed it opened a gloss card instead.
