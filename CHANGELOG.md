# Changelog

Notable changes to targum, newest first. Versions follow the 4-digit
`MAJOR.MINOR.PATCH.MICRO` in `pyproject.toml` and are tagged in git.

## [Unreleased]

### Added
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

### Changed
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
