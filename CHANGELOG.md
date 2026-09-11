# Changelog

Notable changes to targum, newest first. Versions follow the 4-digit
`MAJOR.MINOR.PATCH.MICRO` in `pyproject.toml` and are tagged in git.

## [Unreleased]

### Added
- The chat's shelf says when each text was last opened and finished. "What was the
  last targum I read?" was answered "the list does not keep times" (2026-09-08); the
  reader's own sync had always clocked every open and every chapter finished, and only
  the tool left them out. `search_my_shelf` comes back newest opened first with
  `last_opened`, `days_since_opened` and `finished` on each row and `now` beside the
  list, so the model can count as well as read.
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
  drawer beside the text. Off a disk the reader carries nothing to talk to, and the
  page still fetches nothing by itself.
- A command palette on every page (2026-09-11): ⌘K, or the search in the bar, finds a
  place, a text on your shelf or in the catalogue, or a conversation, and Enter goes
  there — a conversation opens in the drawer.
- The sheet on Learn says how long is left, "about 12 min left", from the sections the
  reader records as finished and the text's own length, and draws it as a line along
  its foot (2026-09-11).

### Changed
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
