# Changelog

Notable changes to targum, newest first. Versions follow the 4-digit
`MAJOR.MINOR.PATCH.MICRO` in `pyproject.toml` and are tagged in git.

## [0.2.0.0] - 2026-09-01

### Added
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
- The serve policy's `media-src` gains `'self'` for the video sidecars
  (design.md §12, "a reader that carries moving pictures").
- Hosted pastes of YouTube links are refused by name with a pointer at the CLI.
- `pyproject.toml` states its licence as an SPDX string with `license-files`, which is
  the current PEP 639 spelling; the table form it used is deprecated.

### Fixed
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
