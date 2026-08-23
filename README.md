# targum

Read a text in the language you are learning with a translation beside it, sentence
by sentence. Tap any word for its dictionary form and what it means, turn Hebrew
vowel points on for a line you are stuck on, keep the words you want, and export
them. Named for the Aramaic word for translation.

## Start

1. **Install it.** [uv](https://docs.astral.sh/uv/getting-started/installation/) is
   the one prerequisite; the quotes around the package name are needed in most
   shells.

   ```
   uv tool install "targum[difficulty]"
   ```

   This pulls a few hundred megabytes, most of it PyTorch. Python 3.11 or newer.

2. **Give it an API key.** Translating goes through Anthropic and costs money —
   cents for an article, more for a book. Get a key at
   [console.anthropic.com](https://console.anthropic.com), then:

   ```
   export ANTHROPIC_API_KEY=...
   ```

   That lasts as long as the Terminal window. To avoid doing it again, put the same
   line in `~/.zshrc` (or `~/.bashrc`).

3. **Run it.**

   ```
   targum serve
   ```

   A page opens in your browser. Drop in an EPUB, a text or markdown file, or paste
   a link — an article, a Wikisource page, `gutenberg:1342`. Say which language you
   are learning, and read.

   Keep the Terminal window open while you read; `Ctrl-C` there stops targum. The
   address it prints carries a key that changes every time it starts, so open it
   from the Terminal rather than from a bookmark.

The price is shown before anything is spent, and finished work is cached, so
nothing is paid for twice. Your readers are saved in `targum-out/`, in whichever
folder you ran `targum serve` from, and they open from there afterwards with no
server running.

The first text in a new language also downloads that language's word model, about
200 MB, once. It happens during the wait after you click **Read this**, and the
Terminal window shows its progress.

## What it does

Readers are one self-contained HTML file per part: no network, no build step. They
work offline, on a phone, and in an e-reader browser — copy a folder out of
`targum-out/` to any device and open `index.html`.

Light or dark is a switch in the corner of every page, and it is one choice for all of
them. Until you touch it targum follows the system setting; after that your choice
wins, in both directions.

Three ways to read, on one control in the corner and on the keys `p`, `i` and `o`:

- **Parallel** — the translation in a column beside the text.
- **Interlinear** — the translation set under each line rather than across a gap
  from it, so a long line does not make your eye travel to find the English.
- **Source only** — the text on its own.

Tap a word for its dictionary form and roughly how common it is, then say how well you
know it: **1** just met it, **2** getting there, **3** nearly know
it, **known**, or **ignore** for a name or a number.

That decision belongs to the word in that language, not to the article you were
reading when you made it. Open anything else in the same language and the words you
are working on are already marked; the ones you know are plain. The panel counts how
much of the text in front of you you already know, which is how you tell whether it
is worth reading yet. Marks fade as a word moves up the scale and go altogether at
*known*, so a text gets quieter as you learn it.

targum does not tell you what a word means unless you ask. The translation is beside
the line, so writing your own meaning is usually quicker than reading a dictionary
entry — and it is the version you will remember. When you want one, **look it up** on
the card fetches that single word, cached so it is free everywhere after that. That is
about half of what a build used to cost: a glossary of every distinct word runs to more
than the translation itself on a short text, and most of it is never read. If you do
want a text glossed from end to end, `targum build --gloss` still buys the lot.

Drag across a few words to keep a phrase; drag across one and targum knows you meant
that word, not a phrase of one. Phrases take a level and your own reading exactly as
words do, and writing either is what keeps them. Words and phrases are two tabs in the
panel, with their own counts and their own exports: a phrase belongs to the text it
was cut from, since outside its sentence it is not anything, and you keep it for its
wording rather than because you did not know it.

The panel shows what turns up in the text in front of you — the words you are working
on that occur here, and the phrases you cut from here — and each tab exports exactly
that.

**Your words** (linked from the library) is everything at once: how many you know and
how many are still coming, what you have kept month by month, and how far into the
rare end of the language you have got. Under the charts is the whole list, searchable
and filterable by how well you know each word, with the phrases grouped by the text
they came from. Both export from there too.

**Sign in and your words follow you.** Without an account everything is kept in the
browser you are reading in, which is fine until that browser is cleared or you pick up
a phone. Signing in is an email address and a link — no password to invent — and from
then on the same list is on every browser you open targum in. Whatever you had kept
before signing in is claimed by the account rather than stranded, and signing out takes
it back off that browser. Running targum yourself, the link is printed in the Terminal
window instead of emailed, and the list is kept in `~/.targum/targum.db`, deliberately
somewhere other than your readers so that clearing those cannot lose it.

Hebrew, Russian, English, Arabic, French, Spanish, German and Latin, with
right-to-left layout done properly. Latin has no frequency data, so its words carry
no difficulty; Arabic works but has had less use than the rest.

**The library page carries a catalogue** of texts that already have a translation
somebody published — the Israeli and American declarations in Hebrew, Tolstoy's *Father
Sergius* in Russian. Building one costs **nothing at all**: no model is asked to
translate anything, the two texts are matched to each other on your machine, and a
translator who lived with a text beats a model that saw it once. Paste a link to a text
that is already in there and targum says so instead of quoting you a price.

A published translation you already have can be aligned the same way. That needs one
more download:

```
uv tool install "targum[difficulty,align]"     # adds a 1.8 GB model, fetched on first use
targum build source.he.md --translation published.en.md
```

Changed how readers look or work? `targum rebuild` rewrites every reader you already
have from the files beside them — nothing fetched, nothing spent.

The same pipeline runs from the command line, and `targum --help` lists the rest:

```
targum build book.epub --to en --words --gloss
```

## Hebrew and vowel points

A Hebrew text gets a vowel-points toggle. Where the source is pointed already — a
Tanakh, a pointed poem — that pointing is what you see, word for word, no model
consulted, and the reader opens with it showing. Where the source is bare, as most
modern writing is, the reader opens bare and the points are guessed by
[Nakdimon](https://github.com/elazarg/nakdimon) if you ask for them: roughly 90%
right on modern Hebrew and 55–73% on classical, which is worth knowing while you
read. On a page where only some sentences are guessed, those are marked.

## What leaves your machine

The text you are reading is sent to Anthropic, to be translated and to have its
words looked up. That is the only thing that goes anywhere. targum never bundles
or uploads a copyrighted translation; the cache, the readers and your word lists
stay where they are.

`targum serve` listens on 127.0.0.1 only and is not a hosted service — see
[SECURITY.md](SECURITY.md).

## Not supported

PDFs, logins, paywalls, and pages that are really web apps. Save a PDF as text or
markdown first.

---

MIT. [NEXT-STEPS.md](NEXT-STEPS.md) is the roadmap, written for contributors.
