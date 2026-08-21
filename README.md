# targum

Turn a text and its translations into a self-contained HTML bilingual reader, built
for comprehensible-input language learning. Named for the Aramaic word for
translation.

```
uv tool install "targum[difficulty] @ git+https://github.com/DLangellotti/targum"
export ANTHROPIC_API_KEY=...
targum serve
```

That opens a local page. Drop in an EPUB, plain text, or markdown file, or paste a
link (an article, a Wikisource page, `gutenberg:1342`), say which language you are
learning, and read. The cost of translating is shown before anything is spent, and
finished work is cached so nothing is paid for twice.

The same pipeline runs from the command line:

```
targum build book.epub --to en --words --gloss
targum build source.he.md --translation published.en.md
```

Readers work offline, on a phone, in an e-reader browser. Tap any word for its
dictionary form and meaning, drag across a phrase to keep it, and export what you
saved as a CSV. A published translation you already have is aligned to the source
sentence by sentence, which beats anything a machine produces. Hebrew, Russian,
English, Arabic, French, Spanish, German, and Latin, with right-to-left layout done
properly.

targum never bundles or uploads a copyrighted translation. The cache, the readers,
and your word lists stay on your machine.

MIT. The roadmap is in NEXT-STEPS.md.
