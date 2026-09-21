# Licensing

targum's own code is **AGPL-3.0-or-later**. Copyright © 2026 David Langellotti. That is
the whole of the licence on everything in this repository, and `LICENSE` is the text of
it. The licence is on the code and not on the name: `NOTICE` says that "targum" is the
project's name and that nothing here grants the right to call a derived product or
service by it.

This file exists because that sentence used not to be the whole story. targum runs on
other people's models, and two of them were licensed for non-commercial use only. The
AGPL promises you may use this software for any purpose including a commercial one, and
for two features that promise was not mine to make. Both are now resolved — the aligner
on 2026-09-02 and the Hebrew annotator the same day — and the history is kept below
rather than deleted, because a supply chain that was once encumbered is a thing anyone
building on targum is entitled to know about.

## The short version

- Install `targum` and use it for anything, commercial included.
- Run the Hebrew annotator and you are using **DICTA**, CC BY 4.0, which permits
  commercial use and asks to be named. targum names it at the foot of every reader whose
  words it read — and, since targum-internal#148, whose modern Hebrew it pointed.
- Nothing in targum is NonCommercial any more. Four things were: the forced aligner until
  2026-09-02; Stanza's Hebrew models until later the same day, except for the sentence
  splitter, which ran on them until 2026-09-03; and Stanza's models for every other
  language, which this document said were clean and were not, until 2026-09-13 — see
  "Stanza's other languages" below.
- A model trained on NonCommercial **or ShareAlike** data is not used (2026-09-13).

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
| nakdimon | MIT | Copyright 2022 Elazar Gershuni; the weights ship in the wheel under the same licence — see below |
| tokenizers, huggingface_hub | Apache-2.0 | load the menaked's and LaBSE's tokenizers and fetch their weights |
| **stanza** | Apache-2.0 (code) | installed, and loads no model: nothing is audited — see below |
| transformers | Apache-2.0 | loads the DICTA weights |

### Optional extras

| Extra | Package | Licence | Notes |
| --- | --- | --- | --- |
| `align` | — | | empty since 2026-09-18: LaBSE is read with transformers |
| `speech-align` | torchaudio, transformers | BSD-2, Apache-2.0 | the acoustic model is Apache-2.0 too |
| `covers` | pillow | MIT-CMU | |
| `difficulty` | wordfreq | Apache-2.0 | the code; its data files are CC BY-SA 4.0 — see below |
| `phonetics` | phonikud | CC BY 4.0 | permissive, attribution required |
| `browser` | playwright | Apache-2.0 | test-only |

`torch` arrives transitively with stanza; its metadata reports
Apache-2.0 for the package and bundles third-party components under their own terms.

## Nothing NonCommercial is left

### Stanza's Hebrew models, which used to be here — resolved 2026-09-02

Stanza itself is Apache-2.0. Its Hebrew models are trained on
[UD_Hebrew-HTB](https://universaldependencies.org/treebanks/he_htb/index.html), which is
CC BY-NC-SA 4.0 and drawn from Ha'aretz — and the Hebrew annotator is what produces the
dictionary forms that targum's whole one-vocabulary-across-biblical-and-modern idea rests
on. It was in the default install rather than an extra.

Whether a NonCommercial term on training data reaches the trained model, and then reaches
that model's output, is genuinely unsettled, and much of the industry proceeds as though
it does not. targum does not rely on that assumption being correct, which is why the
model was replaced rather than reasoned around.

Hebrew is now read by **[DICTA](https://huggingface.co/dicta-il/dictabert-joint)**,
CC BY 4.0. Stanza stays installed and keeps every other language it served; it is simply
never handed a Hebrew word. Annotations made before the swap carry Stanza's name and are
read again — free, because annotating runs on the machine.

**The middle sentence of that paragraph was wrong too, and for longer.** "Keeps every other
language it served" assumed that only Hebrew's treebank was encumbered. Nobody checked.
See the next section.

**That sentence was not true on the day it was written.** The swap moved every Hebrew
word off Stanza and left every Hebrew sentence boundary on it: DICTA takes a sentence at
a time and publishes no splitter, so each sentence it was handed had been cut by Stanza's
Hebrew tokenizer, trained on the same treebank (targum-internal#146). Since 2026-09-03
Hebrew sentences are drawn by rule in `segment/hebrew.py`, and Stanza refuses a Hebrew
text outright rather than being trusted not to receive one; a test pins both, and the
default annotator was closed the same day, since four callers — the gloss command and three
that measure — still built it with Stanza alone. No Hebrew text now passes through a Stanza pipeline at any stage —
segmentation, annotation or difficulty — and the credit at the foot of a reader that
names DICTA is, from that date, the whole truth.

Measured before the switch, on the 47 readers' stored segmentation: the rules and Stanza
differ at 2,768 boundary positions against the 18,490 Stanza drew (15.0%, an upper bound
since a boundary that shifts counts twice), and nearly all of the difference is
exclamation marks, which Stanza's Hebrew tokenizer had never once split on. The same
day's review found the lemmatizer routing on the raw language tag, so a text tagged
`he-IL` or `iw` had been reaching Stanza's Hebrew models since the swap; it routes by
code now, and Stanza's lemmatizer refuses Hebrew the way its segmenter does. Texts already on a shelf keep the
segmentation they were translated under — the pipeline reuses it by document hash — so
the switch bought no translation again. A forced rebuild of everything would re-buy 2,227
translated segments, about $5.77, and re-annotate and re-time every one of them, which is
the actual reason nothing forces one.

### Stanza's other languages — resolved 2026-09-13

Every Stanza model is trained on a Universal Dependencies treebank, and each treebank has
a licence of its own. Checked against the treebank pages on 2026-09-13, for the default
package of every language targum could reach:

| Language | Stanza default | Trained on | Worst licence |
| --- | --- | --- | --- |
| English | `combined` | EWT, GUM, GUMReddit, PUD | GUM: **CC BY-NC-SA 4.0** |
| Russian | `syntagrus` | SynTagRus | **CC BY-NC-SA 4.0** |
| Italian | `combined` | ISDT, VIT, PoSTWITA, TWITTIRO | ISDT, VIT: **CC BY-NC-SA 3.0** |
| Arabic | `padt` | PADT | **CC BY-NC-SA 3.0** |
| Latin | `ittb` | ITTB | **CC BY-NC-SA 3.0** |
| French | `combined` | GSD, ParisStories, Rhapsodie, Sequoia | Sequoia LGPL-LR; the rest CC BY-SA 4.0 |
| Spanish | `combined` | AnCora, GSD | GSD CC BY-SA 4.0 |
| German | `combined` | GSD, with Wiktionary lemmas | CC BY-SA 4.0 |

The English row is the one that ran. A published translation is split into sentences
before it is lined up against the Hebrew, and every build of a Global Voices article or a
declaration split its English with that model — eleven alignments on the laptop's shelf.
One Russian reader was lemmatized with SynTagRus.

**The rule, stated so the next language meets it in writing:** a model is not used when
what it was trained on carries a NonCommercial term *or a ShareAlike one*. NonCommercial
for the reason Hebrew's section gives. ShareAlike because it is the one door the
evaluation data below is kept behind, for the same reason: a model tuned on it may carry
the term into what it makes, and what targum makes is the corpus. On that rule none of
the rows above passes; the only clean single treebanks are tiny (Italian MarkIT, CC BY
4.0, 38 thousand tokens) or Spanish AnCora alone.

So Stanza now reads nothing unless `segment/stanza_segmenter.AUDITED` names the language
and the exact build that was checked — never Stanza's default, which a release can point
at a different treebank. `AUDITED` is empty. The download, the tokenizer and the
lemmatizer all refuse an unlisted language before anything is imported or fetched, and
`hbo`, which walked past a check on the literal `he`, is refused with the rest. Sentences
in a script with capitals are drawn by rule in `segment/cased.py`, the Hebrew rules taught
case and a short abbreviation list per language; a script without capitals is left whole.
A language with no audited lemmatizer builds with its text and translation and no word
cards, as Yiddish always has. Before a language is added to `AUDITED`, its tokenizer's
pretrained vectors (`conll17`) and character language models are checked as well: they
are separate downloads with sources of their own.

What did not need doing again: no translation is bought, because a text on a shelf keeps
its stored segmentation. The eleven alignments are keyed on the segmenter now and line up
again for nothing, and the Russian reader keeps its annotation until it is rebuilt.

**What the swap cost, measured rather than asserted** (targum-internal#116, 47 readers):
the two agree on 75% of tokens, DICTA declines to lemmatize 3.7% of them where 1900s
orthography is out of its vocabulary, and the surface form is used there. DICTA tags no
binyan at all, so the binyan and the root derived from it were recovered from the lemma's
own spelling where that is unambiguous and left off where it is not — verb roots landed
at 26% of verbs against Stanza's 51%. Against that, DICTA keeps the personal pronouns
apart where Stanza's treebank collapsed אני, לי and בו onto one card, and its prefix
segmentation is what #110 was opened about.

**And what has been bought back since**, against a hand tagging rather than against
Stanza — see the treebanks below. The biblical half reads its binyan and root off the
Open Scriptures morphology, which had them all along: 97.9% and 99.9% of verbs, from
1.7% and 1.1%. On the modern half a per-word dictionary supplies the binyan for 96.7% of
verbs and the root for 99.1%, at 94.3% and 98.1% accuracy, where the spelling rules
answered for 8.9%. Neither depends on anything NonCommercial and neither moves a lemma.

### DICTA's menaked — CC BY 4.0, confirmed 2026-09-07

Modern Hebrew is pointed by
**[`dicta-il/dictabert-large-char-menaked`](https://huggingface.co/dicta-il/dictabert-large-char-menaked)**,
whose card carries `license: cc-by-4.0` in its front matter and the Creative Commons
Attribution 4.0 International text in its body. The weights are 1.2 GB, fetched from
Hugging Face by `targum models fetch menaked` (or `fetch he`, with the annotator's) into
the model directory, and never vendored: no copy of them is in this repository or in the
wheel, and a machine without them points with Nakdimon and says so. This is the local run
the card's licence permits; DICTA's hosted Nakdan is CC BY-NC-SA by its site terms and is
never called (`vocalize/dicta.py`).

Measured before it was let near a reader, against two held-out sets, on 2026-09-07
(`scripts/measure_pointing.py`, `evals/ledger.jsonl`, stage `vocalize`): on DICTA's own
Wikipedia test corpus — public domain per its README — 0.969 to Nakdimon's 0.960 on
vowels per letter and 0.890 to 0.854 on exact words; on pointed prose and poetry from
Project Ben-Yehuda, public domain, by twelve authors none of whom is in Nakdimon's
training set, 0.906 to 0.893 and 0.700 to 0.677. Its card says it is not for biblical,
rabbinic or premodern Hebrew, and the register gate in `vocalize.for_source` keeps those
shelves on Nakdimon; scripture and the pinned editions reach neither model.

The credit is at the foot of every reader whose pointing it made, beside the annotator's
and keyed the same way: to the vocalizer that actually ran, and only where it pointed a
word the edition had not. A reader pointed by Nakdimon, or by its edition, carries no
DICTA credit for its vowels.

### Nakdimon's weights — MIT, confirmed 2026-09-02

The diacritizer's model is `nakdimon/data/Nakdimon.onnx`, 21 MB inside the `nakdimon`
wheel on PyPI, so every install of targum redistributes it and the box serves its output
commercially. The wheel carries one licence, MIT (Copyright 2022, Elazar Gershuni), the
PyPI classifier and the [repository](https://github.com/elazarg/nakdimon) say the same,
and the model file has no licence of its own and no model card. MIT grants use, copy,
distribution, sublicensing and sale, on the condition that the copyright and permission
notice travel with any copy. So the weights may be redistributed, and the notice above is
kept for that reason.

The training corpus is the caveat, the same shape as Stanza's and weaker.
[`elazarg/hebrew_diacritized`](https://github.com/elazarg/hebrew_diacritized) has no
licence at all, and the paper says why: its authors were "unaware of legally-obtainable
dotted modern corpora", so the modern portion is copyrighted prose — books, news, forums,
Wikipedia — dotted with Dicta's API and corrected by hand, and the pre-modern portion
comes from Project Ben-Yehuda, Mechon Mamre and the Short Story Project. No one in that
chain attached a NonCommercial term. Whether an unlicensed corpus reaches the weights is
the same unsettled question recorded under Stanza, and targum takes the same position: it
does not rely on the answer, and says so here.

### The forced aligner, which used to be here — resolved 2026-09-02

The `speech-align` extra installed
[ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner), CC BY-NC 4.0,
on `MahmoudAshraf/mms-300m-1130-forced-aligner`, a model in Meta's MMS lineage and
NonCommercial as well. It was the only thing in targum that produced word-level timings
for a recording, so every timing targum held had been made by a NonCommercial tool.

It is gone. The algorithm was never the encumbered part: CTC forced alignment is
`torchaudio.functional.forced_align`, which is BSD-2. Only the acoustic model carried the
term, so only the acoustic model changed —
[`imvladikon/wav2vec2-large-xlsr-53-hebrew`](https://huggingface.co/imvladikon/wav2vec2-large-xlsr-53-hebrew),
Apache-2.0, fine-tuned from XLS-R (Apache-2.0) on Common Voice (CC0). Nothing in that
chain restricts use.

**The lockfile kept it three days longer than the code did.** `pyproject.toml` stopped
requiring `ctc-forced-aligner` on 2026-09-02, but `uv.lock` was not regenerated, so it
stayed pinned as a dependency of the `speech-align` extra — and `uv sync --extra
speech-align` went on installing a CC BY-NC package that nothing imported. The claim
above was true of the source and false of an install. Regenerated 2026-09-03; the lock
now resolves `torchaudio` and the six packages that came in behind the old aligner —
`nltk`, `uroman`, `torchcodec`, `unidecode`, `defusedxml` — are gone with it.

A licence audit that reads the manifest and not the lock will keep finding this class of
thing, since the lock is what a machine actually installs.

Measured against the spans the old aligner produced for the same reading, rather than
asserted: over 408 words of a Ben-Yehuda recording the two agree to a median of **20 ms**,
with 96% of word starts inside 100 ms — and the new one runs at 0.20 minutes per minute
of audio against the old one's 0.65. It also aligns Hebrew *as Hebrew*: MMS reached the
language by romanising it first, so every span was decided in a transliteration, where
this model's vocabulary is the Hebrew alphabet with its final forms.

Timings made before the swap carry the old aligner's name and are re-derived.

### What CC BY 4.0 asks of targum, and where it is given

DICTA's terms permit commercial use and require attribution. The naming is at the foot of
every reader whose words DICTA read — beside the credit for whoever read the audio, and
for the same reason: a credit in a file nobody opens is not a credit. It is keyed to the
annotator that actually ran, so a reader built before the swap does not claim a credit it
did not earn. The vowel points have their own line on the same terms, keyed to the
vocalizer that ran and shown only where it pointed something.

A second DICTA model was tried and not adopted. `dicta-il/dictabert-char-spacefix`
(licence field `cc-by-4.0` on its card, 2026-09-07) restores missing spaces, and
targum-internal#151 asked whether it could propose seams that `ingest/spacing.py`'s
rules cannot see. It was run once, locally, over the 1,667 unknown-and-splittable words
on the shelf: it passed the issue's bar on 96 and every one of them was a loanword, an
Aramaic form or a name rather than a glued pair (`scripts/measure_glue.py --spacefix`).
So it is not part of any install, no reader is built with it, and the credit at the foot
of a reader does not name it. The hosted DICTA tools, NonCommercial by their terms, were
not called.

The biblical half never needed a model at all: the Tanakh is looked up in the Open
Scriptures morphology, CC BY 4.0, hand-tagged.

This is the honest state of the supply chain.

### wordfreq's frequency tables — CC BY-SA 4.0, and an open decision (2026-09-13)

This table said wordfreq's data was "mixed". It is more precise than that, in wordfreq's
own words: the code is Apache-2.0, and "it includes data files that may be redistributed
under a Creative Commons Attribution-ShareAlike 4.0 license", built from Google Books
Ngrams, Wikipedia, the Leeds Internet Corpus, ParaCrawl, OpenSubtitles and the SUBTLEX
lists. Every difficulty band a reader sees, in Hebrew since the first build and in French,
Russian and Italian now, is a word's place in one of those tables.

What that does and does not reach, as this document reads it: a band is a fact about a
word (how common it is), computed at build time and never the table itself, so no
wordfreq file is redistributed by a reader. What would be a redistribution is shipping a
list derived from the tables, and the CEFR lemma lists planned for `annotate/cefr/` are
exactly that; they would go out under CC BY-SA 4.0 with wordfreq credited, which the
content rule below permits for a business. The ShareAlike rule decided on 2026-09-13 is
about **models trained on** ShareAlike data, and wordfreq is not a model. Whether the
same caution should reach a frequency table is not decided here, and is written down so
that it is decided rather than drifted into.

### OpenRussian's tables — CC BY-SA 4.0, looked up and never shipped (2026-09-14)

A Russian verb's card names its aspect partner, and a word whose stress moves across its
forms says where (targum-internal#259). Both come from
**[OpenRussian.org](https://en.openrussian.org)**'s dictionary tables
([`Badestrand/russian-dictionary`](https://github.com/Badestrand/russian-dictionary),
LICENSE: CC BY-SA 4.0), which were built from Wiktionary and corrected by the site's
users. They are pinned to one commit (`annotate/openrussian.COMMIT`) and fetched by
`targum models fetch openrussian` into the model directory. No copy is in this repository
or the wheel, and a test fails if a row of one ever is.

David decided on 2026-09-14 how they may be used: **as a lookup, attributed, never
trained on, and never shipped as a list of their own.** What reaches a reader is a fact
about one word, such as говори́ть being сказа́ть's partner or рука́ being ру́ку in the
accusative. That is the same reading this document gives wordfreq's bands above. A page
that shows one names and links OpenRussian and the licence at its foot. The ShareAlike rule
is about models trained on ShareAlike data, and nothing here is a model.

The dictionary's README says its data "is not void of flaws". So a spelling it files
twice (за́мок and замо́к, the two писать) gets no partner and no stress line.

### silero-stress — MIT, training data not disclosed (2026-09-14)

Russian stress marks are proposed by
**[silero-stress](https://github.com/snakers4/silero-stress)**. It is installed by the
`stress` extra, which the deploy includes. The wheel on PyPI carries its weights (38 MB)
and one licence, MIT (Silero Team), which grants use, copying and sale on condition that
the notice travels with any copy. So targum may redistribute it and serve its output
commercially, as with Nakdimon above.

The caveat is also Nakdimon's. Its README says it was trained on "~4M known words and word
forms and ~120M annotated sentences with homographs" and does not say where those came
from. Its authors wrote that the Russian National Corpus was not used
([Habr, 2025](https://habr.com/ru/articles/955130/)). On 2026-09-14 David accepted it on
those terms, and it is recorded here so the acceptance is a decision rather than a drift.
The alternatives were checked and refused: RUAccent was trained on the RNC and Wikipedia
(CC BY-SA), Omogre is CC BY-NC-SA, and every model built from Zaliznyak's dictionary
inherits its NonCommercial grant.

silero proposes, but no mark rests on it alone. `vocalize/stress.py` places a mark only
where OpenRussian's tables (above) allow the word a single stress and silero chose it.
Measured on 1,000 sentences stressed by hand in Wiktionary (`scripts/eval_stress.py`,
evaluation only), marks placed that way were right 99.8% of the time, against 98.5% for
silero alone.

### Grammalecte's French lexicon — MPL 2.0, counted and not shipped (2026-09-15)

A French noun's card names the ending that tells its gender, where the noun agrees: *nation*
reads "noun · f · like most nouns in -tion" (targum-internal#263). Which endings earn that
line is counted from **[Grammalecte](https://grammalecte.net)**'s lexicon
(`lexicons/French.lex`, the successor to the Dicollecte dictionary). Its header gives the
Mozilla Public License 2.0. The count reads the lexicon at one commit of its GitHub mirror
([`Pofilo/grammalecte`](https://github.com/Pofilo/grammalecte), `08511c22`), cached outside
the repository by `scripts/french_endings.py`.

What ships is `annotate/french_endings.json`: about 160 endings, each with a gender, the share
of nouns that have it and how many nouns that is. Only endings shared by 90% or more of at
least fifty plain nouns are kept. That is a statistic about the lexicon, not a copy of any
part of it, so this document reads MPL 2.0's file-level conditions as not reaching it. It is
the same reading as wordfreq's bands and OpenRussian's facts above. The source and its
licence are named in the table itself anyway. The card said to count from Dicollecte rather
than from Lexique, which is CC BY-SA, and this does. Lefff (LGPL-LR) was kept in reserve
as a lookup for nouns this lexicon lacks, and was not needed.

## Content is not code

Nothing above covers what targum *reads*. A text, a translation and a recording each
carry their own licence, held per source and shown to the reader: the foot of a reader
credits whoever read it and links the licence it came under. Library content is not in
this repository and is not covered by the AGPL.

**A reader's own import is theirs, and it is not gated on licence.** What a reader
brings to their own shelf — a link, a file, a recording, and since 2026-09-05 anything
the chat finds for them — is their act on content they had lawful access to. It is
refused only on what is not about permission: an address the fetch door will not open,
a format the ingester does not read, the money and hours rails. The licence is
**recorded** on every import (`licensing.verdict`, `screen.licence_flags`) and never
enforced against the reader; it is read later, at the one moment a private thing might
become public, which is promotion into the catalogue and the corpus — and there
`Standing.unknown` stays private for ever. The chat's server-side search is held to a
list of hosts (`chat/sources.py`) for relevance, not permission; whatever it surfaces
passes the same doors as a pasted link.


The bar for a recording is that no-derivatives terms are refused outright — segmenting,
transcribing and aligning are adaptations, and no access policy cures an ND term.
ShareAlike is accepted, which means the segments cut from such a recording carry
ShareAlike onward.

### The treebanks the annotator is scored against, which never ship

Until 2026-09-03 every number targum gave for its Hebrew annotation was one annotator
measured against another, which cannot tell a correct answer from a shared mistake. The
annotator is now scored against the **IAHLT** treebanks — `UD_Hebrew-IAHLTwiki` and
`UD_Hebrew-IAHLTknesset`, through Universal Dependencies — which carry the lemma, part
of speech and binyan of every word, written down by people.

**They are CC BY-SA 4.0, which is the one door the text bar keeps shut**, so they are
used for exactly one thing. Nothing is trained on them, nothing derived from them is
served, and no build reads them. They are fetched to `targum models fetch gold`, sit
beside the language models, and a scorecard is computed from them on a developer's
machine: evaluation, which is not a commercial use and produces no derivative to carry
the term onward. Their whole contribution to the corpus is a number in a commit message.

If that ever stops being true — if a model is tuned on them, or a table derived from them
ships — the ShareAlike term reaches the corpus and this paragraph is wrong. It is written
down here so that would have to be a decision rather than a drift.

### FLORES+, which the chat's recast is scored against, and which never ships

The chat opens every reply with the reader's line recast into Hebrew, and since
2026-09-07 that line is measured against a Hebrew a person wrote of the same English
(`scripts/eval_recast.py`; targum-internal#219). Tatoeba is one reference for that and
three volunteers wrote most of it. **FLORES+** (`openlanguagedata/flores_plus`, the Open
Language Data Initiative) is the other: 2,009 sentences from 842 web articles, each
rendered into Hebrew by a professional translator, and the same sentences in two hundred
languages, so the number is one anybody can set beside their own (targum-internal#221).

**It is CC BY-SA 4.0, which is the one door the text bar keeps shut**, so it is used
for exactly one thing, on the terms the treebanks above set. Nothing is trained on it,
nothing derived from it is served, and no build reads it. It is fetched by `targum
models fetch flores` to the same directory as the gold sets, with the operator's own
Hugging Face token because the dataset is gated, and the recast is scored against it on
a developer's machine. Its whole contribution to the corpus is a row in
`evals/ledger.jsonl` with `corpus=flores-plus`.

**NTREX-128** (`MicrosoftTranslator/NTREX`, Microsoft Translator) stands beside it on
the same terms: the WMT 2019 news test set, 1,997 English sentences with a professional
Hebrew rendering each, CC BY-SA 4.0, fetched by `targum models fetch ntrex` to the same
directory and used for the same one thing, as `corpus=ntrex-128`. Two references in two
registers keep the recast number from being one corpus's house style
(targum-internal#222).

If that ever stops being true of either — if a sentence reaches a prompt the way
Tatoeba's do, or a page — the ShareAlike term reaches whatever it touched and this
paragraph is wrong. It is written down here so that would have to be a decision rather
than a drift.

### The Universal Dependencies dev sets the model's dictionary forms are scored against, which never ship

French, Russian, Italian and Yiddish words are read by the model (`annotate/model_lemma.py`)
because no Stanza model for them clears the bar above. What the model returns is scored
against the dev split of a Universal Dependencies treebank per language
(`scripts/eval_lemma.py`): **French GSD** (CC BY-SA 4.0), **Russian SynTagRus** (CC BY-NC-SA
4.0), **Italian ISDT** (CC BY-NC-SA 3.0) and **Yiddish YiTB** (CC BY-SA 4.0). Two of those
are NonCommercial, which is exactly why they are fine here and nowhere else: nothing is
trained on them, no prompt carries a sentence of them, no build reads them, and nothing
derived from them is served. They are downloaded to the model directory on a developer's
machine, and their whole contribution is rows in `evals/ledger.jsonl` under
`stage=lemma`. The same sentence as FLORES+'s applies: if one ever reaches a prompt or a
page, this paragraph is wrong, and that has to be a decision rather than a drift.

### HeQ, which the chat's answers about a text are scored against

The chat answers a question about the text on the reader's screen, in English, and
nothing measured whether the answer was right. **HeQ** — 30,147 reading-comprehension
questions over 4,401 paragraphs of Hebrew Wikipedia and Geektime, each answered by a
person with the span of the paragraph that answers it; annotated by Webiks for MAFAT
under the National NLP Plan of Israel — is the reference (`chat/heq.py`,
`scripts/eval_ask.py`; targum-internal#223).

**It is CC BY 4.0**: attribution, nothing else owed, and the licence `licensing.verdict`
marks exportable. It is used for one thing all the same. Nothing is trained on it
(targum-internal#161's row is evaluation), nothing derived from it is served, and no
build reads it; it is fetched by `targum models fetch heq` to the directory the gold
sets sit in, and its contribution to the corpus is a row in `evals/ledger.jsonl` with
`corpus=heq`. The credit the licence asks for is here, and in the module's header. Its
paragraphs would pass the text bar as a shelf, and that is a separate decision, not this
one.

### Tatoeba's sentences, which the chat reads for the idiom

Since 2026-09-07 the chat is handed a few sentences a Hebrew speaker wrote, inside the
reader's own words, so that what it writes is shaped like Hebrew rather than translated
from English (`chat/exemplars.py`; targum-internal#218). They come from **Tatoeba**
(tatoeba.org), whose sentences are **CC BY 2.0 FR**: attribution, nothing else owed, and
the licence `licensing.verdict` marks exportable. The same sentences are the reference
the chat's recast is scored against (`scripts/eval_recast.py`) and the openers the
grading eval draws (`scripts/eval_grading.py --pool`).

**What is taken.** Only sentences whose contributor declares Hebrew native, each with a
linked English sentence — 165,000 of Tatoeba's 212,000 Hebrew sentences on 2026-09-07,
three contributors writing most of them — filtered and lemmatized by
`scripts/tatoeba_pool.py` on a developer's machine into a file the box reads
(`TARGUM_EXEMPLARS`, or `exemplars.jsonl` beside `sources.json`). The file is data and
does not ship in the wheel or the repository. Tatoeba's audio is licensed per recording
and most Hebrew recordings carry no reuse licence; none is taken.

**And since 2026-09-21, the Russian too.** targum-internal#286 asks what a Russian
reader's recast is worth, and #222 had settled that Tatoeba is the recast's yardstick —
so the Russian number has to be taken here. `scripts/tatoeba_russian.py` joins Tatoeba's
own `heb-rus` link file onto the pool, adding a Russian sentence to **6,682** of the
165,454 rows. It is the same licence and the same terms: CC BY 2.0 FR, per sentence, per
contributor, nothing else owed. Nothing is lemmatized again and no audio is taken.

**Where the credit is given.** Here, and in every row of the pool, which keeps the
username of the Hebrew contributor, of the English one and — on a row that has one — of
the **Russian** one (`ru_by`), with the sentence's own address
(`tatoeba.org/sentences/show/<id>`). The sentences reach the model as a prompt
and reach no page: a reader is shown the chat's own lines, which the contract asks it to
write itself. If a Tatoeba sentence ever appears verbatim in a reader's saved
conversation, that build's `licence` and `credit` fields are where the attribution
travels; the promotion door (`promote.py`) reads them before anything becomes public.

**Nothing trains on them.** targum-internal#161's standard is a documented grant covering
the use made; CC BY would permit it, and nothing does it, because nothing here trains.

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
| **free** | public domain or CC0, or targum's own writing (`targum`). Nothing is owed; credited anyway. |
| **owed** | usable commercially, and something travels with it — a credit, or ShareAlike. |
| **closed** | NonCommercial, or anything NoDerivatives touches. Not usable in a paid offering. |
| **unknown** | nothing recorded, or terms nobody here recognises. **Not** treated as free. |

Two of these are easy to get backwards and both are load-bearing. **ShareAlike does not
block a business**: CC BY-SA permits commercial use and requires derivatives to go out
under the same terms, so a corpus built on it can be sold and cannot be kept secret.
**NonCommercial is the term that closes a door**, because it bites on the commercial
character of the offering rather than on which individual reader paid.

**Texts record it on the catalogue row.** Since 2026-09-08 every entry carries
`licence`, `credit` and `licence_url`, filled by `scripts/backfill_licences.py` from what
the source itself says and from nothing else: the edition's licence off Sefaria's API for
a Sefaria or siddur text, the Creative Commons link in the page's own footer for a news
article, Project Ben-Yehuda's public-domain terms for its texts, the curation record for
a video, and `targum` for the dialogues targum wrote. A page that says nothing is left
empty and listed, which `targum licences` reports as unknown — the seven Hebrew
Wikisource pages, on the day this was written (targum-internal#115).

Ask the corpus rather than remember it:

```
targum licences
```

It lists every source by standing, says how many may leave, and names the ones with
nothing recorded so they can be checked.
