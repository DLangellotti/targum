# targum

Read a text in the language you are learning with a translation beside it, sentence by
sentence. Tap any word for its dictionary form and what it means, keep the words you
want, export them. Named for the Aramaic word for translation.

Hebrew, Russian, English, Arabic, French, Spanish, German and Latin, right-to-left
done properly.

## Start

[uv](https://docs.astral.sh/uv/getting-started/installation/) is the one prerequisite.
Python 3.11 or newer. The install pulls a few hundred megabytes, most of it PyTorch.

```
uv tool install "targum[difficulty]"
export ANTHROPIC_API_KEY=...      # a key comes from console.anthropic.com
targum serve
```

A page opens. Drop in an EPUB, text or markdown file, or paste a link — an article, a
Wikisource page, `gutenberg:1342`. Keep the Terminal window open while you read;
`Ctrl-C` stops it. The address carries a key that changes every start, so open it from
the Terminal rather than a bookmark.

Translating costs money — cents for an article, more for a book. The price is shown
before anything is spent, and finished work is cached. Readers are saved in
`targum-out/` and open from there afterwards with no server running.

## What it does

Readers are one self-contained HTML file per part: no network, no build step. They work
offline, on a phone, and in an e-reader browser.

Three ways to read — parallel, interlinear, source only — on the keys `p`, `i` and `o`.
Tap a word to see how common it is and say how well you know it; that belongs to the
word in that language, not to the text you were reading. Drag across a few words to
keep a phrase. Sign in with an email address and a link and the list follows you to
every browser; without an account it stays in the one you are reading in.

The library carries a catalogue of texts that already have a published translation. The
catalogue itself is data, not code, and is not in this repository: `targum` reads it from
`~/.targum/catalogue.json` (or the path in `TARGUM_CATALOGUE`), and without one the
library is simply empty.
Building one of those costs nothing: the two texts are matched on your machine and no
model is asked to translate anything. Your own published translation aligns the same
way, with `uv tool install "targum[difficulty,align]"` and:

```
targum build source.he.md --translation published.en.md
```

`targum rebuild` rewrites every reader you already have. `targum --help` lists the rest.

## Hebrew vowel points

Where the source is pointed, that pointing is what you see, no model consulted. Where
it is bare, points are guessed on request by
[Nakdimon](https://github.com/elazarg/nakdimon) — roughly 90% right on modern Hebrew,
55–73% on classical. Guessed sentences are marked.

Those vowels are also what lets a word say how it is said. Install with
`uv tool install "targum[phonetics]"` and tapping a word shows its reading, stress
marked — בָּצָל is `batsˈal` and בְּצֵל is `btsˈel`, the same four letters read two ways,
and which one it is depends on the sentence rather than the dictionary. Read on your
machine by [Phonikud](https://phonikud.github.io/), and only ever for a word that has
vowels above it: a word with no reading shows none. Vocal shva is the weak point, so
בְּאֶרֶץ comes out a syllable short.

## What leaves your machine

Translating a text, and looking up a word, sends that text to Anthropic.

Signing in sends your email address, the words you have saved — the dictionary form,
your own meaning, your notes — and the phrases you have cut, which are the actual words
you picked out of what you were reading. They are kept on the server you signed in to.
Stay signed out and all of it stays in the browser instead.

Tapping *conjugations* on a Hebrew verb opens Pealim in a new tab.

Nothing else goes anywhere. Your readers, the cache and the build artifacts stay on
disk, and a translation you supplied is never uploaded. `targum serve` listens on
127.0.0.1 only and is a single-user tool, not a hosted service — see
[SECURITY.md](SECURITY.md).

## Not supported

PDFs, logins, paywalls, and pages that are really web apps.

---

## Licence

AGPL-3.0-or-later. Copyright © 2026 David Langellotti.

Read it, run it, change it. The one condition that bites: if you run a changed version
as a service other people use, they are entitled to your changes. Full terms in
[LICENSE](LICENSE).
