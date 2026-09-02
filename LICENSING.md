# Licensing

targum's own code is **AGPL-3.0-or-later**. Copyright © 2026 David Langellotti. That is
the whole of the licence on everything in this repository, and `LICENSE` is the text of
it.

This file exists because that sentence is not the whole story. targum runs on other
people's models, and two of them are licensed for non-commercial use only. The AGPL
promises you may use this software for any purpose including a commercial one. For most
of targum that promise is good. For two features it is not mine to make, and saying so
here is better than letting you find out downstream.

## The short version

- Install `targum` and use it for anything, commercial included.
- Install `targum[speech-align]`, or run the Hebrew annotator, and you are using a model
  licensed **NonCommercial**. That restriction comes from the model's authors, not from
  targum, and the AGPL cannot lift it.

## Direct dependencies

| Package | Licence | Notes |
| --- | --- | --- |
| typer | MIT | |
| rich | MIT | |
| pydantic | MIT | |
| jinja2 | BSD-3-Clause | |
| httpx | BSD-3-Clause | |
| beautifulsoup4 | MIT | |
| trafilatura | Apache-2.0 | |
| anthropic | MIT | client only; the API behind it is a paid service |
| nakdimon | MIT | Copyright 2022 Elazar Gershuni |
| **stanza** | Apache-2.0 (code) | **the Hebrew models are the problem — see below** |

### Optional extras

| Extra | Package | Licence | Notes |
| --- | --- | --- | --- |
| `align` | sentence-transformers | Apache-2.0 | |
| **`speech-align`** | **ctc-forced-aligner** | **CC BY-NC 4.0** | **NonCommercial. See below.** |
| `covers` | pillow | MIT-CMU | |
| `difficulty` | wordfreq | Apache-2.0 | the code; its frequency data is mixed |
| `phonetics` | phonikud | CC BY 4.0 | permissive, attribution required |
| `browser` | playwright | Apache-2.0 | test-only |

`torch` arrives transitively with stanza and sentence-transformers; its metadata reports
Apache-2.0 for the package and bundles third-party components under their own terms.

## The two NonCommercial pieces

### `ctc-forced-aligner` — CC BY-NC 4.0

The `speech-align` extra installs
[ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner), which
publishes under CC BY-NC 4.0 and downloads `MahmoudAshraf/mms-300m-1130-forced-aligner`,
a model in Meta's MMS lineage, also NonCommercial.

This is the only thing in targum that produces word-level timings for a recording. It is
opt-in, it is not vendored, and pip fetches it separately — so this repository does not
redistribute it. But `src/targum/audio/align.py` imports it, and a reader who installs
the extra to align a commercial audiobook is doing something the model's licence does not
permit. That is worth knowing before you build on it.

### Stanza's Hebrew models — CC BY-NC-SA 4.0, upstream

Stanza itself is Apache-2.0. Its Hebrew models are trained on
[UD_Hebrew-HTB](https://universaldependencies.org/treebanks/he_htb/index.html), which is
CC BY-NC-SA 4.0 and drawn from Ha'aretz. The Hebrew annotator is what produces the
dictionary forms that targum's whole one-vocabulary-across-biblical-and-modern idea rests
on, and it is in the default install rather than an extra.

Whether a NonCommercial term on training data reaches the trained model, and then reaches
that model's output, is genuinely unsettled — and much of the industry proceeds as though
it does not. targum does not rely on that assumption being correct. It is recorded here
so that anyone building on targum can make their own call rather than inherit mine.

## What targum is doing about it

Both are being replaced with permissively licensed Hebrew models rather than worked
around. [DICTA](https://huggingface.co/dicta-il) publishes `dictabert-morph` and
`dictabert-seg` under CC BY 4.0, which permits commercial use with attribution, and CTC
forced alignment is a free algorithm whose only encumbered part is the acoustic model.
The tracking issues live on the private board; this file is updated when the swap lands.

Until it does, this is the honest state of the supply chain.

## Content is not code

Nothing above covers what targum *reads*. A text, a translation and a recording each
carry their own licence, held per source and shown to the reader: the foot of a reader
credits whoever read it and links the licence it came under. Library content is not in
this repository and is not covered by the AGPL.

The bar for a recording is that no-derivatives terms are refused outright — segmenting,
transcribing and aligning are adaptations, and no access policy cures an ND term.
ShareAlike is accepted, which means the segments cut from such a recording carry
ShareAlike onward.

### The Hebrew Bible is read, not analysed

Scripture on the shelf is not annotated by a model. Its prefix divisions, lemmas and
morphology come from the **Open Scriptures Hebrew Bible Project**, under **CC BY 4.0**,
with the Westminster Leningrad Codex beneath them in the public domain, and the Strong's
and Brown-Driver-Briggs lexicons likewise public domain under a CC BY 4.0 compilation.

Credit is required by that licence and is given here, in `annotate/oshb.py`, and by
`targum models fetch scripture` when the data arrives.

It is fetched rather than vendored, into the model directory beside the language models,
and converted once on arrival — so a reader build parses no XML and fetches nothing.

### What is recorded, and how to ask

Each source keeps the licence as its source writes it, verbatim, together with the URL
where that claim was read — kept verbatim precisely so it can be re-checked against the
page rather than against somebody's summary of it.

What the licence *allows* is not stored beside it. It is computed, in `licensing.py`,
so there is one answer rather than a field that has to be kept true:

| standing | meaning |
| --- | --- |
| **free** | public domain or CC0. Nothing is owed; credited anyway. |
| **owed** | usable commercially, and something travels with it — a credit, or ShareAlike. |
| **closed** | NonCommercial, or anything NoDerivatives touches. Not usable in a paid offering. |
| **unknown** | nothing recorded, or terms nobody here recognises. **Not** treated as free. |

Two of these are easy to get backwards and both are load-bearing. **ShareAlike does not
block a business**: CC BY-SA permits commercial use and requires derivatives to go out
under the same terms, so a corpus built on it can be sold and cannot be kept secret.
**NonCommercial is the term that closes a door**, because it bites on the commercial
character of the offering rather than on which individual reader paid.

Ask the corpus rather than remember it:

```
targum licences
```

It lists every source by standing, says how many may leave, and names the ones with
nothing recorded so they can be checked.
