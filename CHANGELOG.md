# Changelog

Notable changes to targum, newest first. Versions follow the 4-digit
`MAJOR.MINOR.PATCH.MICRO` in `pyproject.toml` and are tagged in git.

## [0.2.0.0] - 2026-09-01

### Added
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
