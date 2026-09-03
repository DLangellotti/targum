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
  words it read.
- Nothing in targum is NonCommercial any more. Two things were: the forced aligner until
  2026-09-02, and Stanza's Hebrew models until later the same day — except for the
  sentence splitter, which the swap overlooked and which ran on them until 2026-09-03.

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
| **stanza** | Apache-2.0 (code) | Hebrew is no longer read by it — see below |
| transformers | Apache-2.0 | loads the DICTA weights |

### Optional extras

| Extra | Package | Licence | Notes |
| --- | --- | --- | --- |
| `align` | sentence-transformers | Apache-2.0 | |
| `speech-align` | torchaudio, transformers | BSD-2, Apache-2.0 | the acoustic model is Apache-2.0 too |
| `covers` | pillow | MIT-CMU | |
| `difficulty` | wordfreq | Apache-2.0 | the code; its frequency data is mixed |
| `phonetics` | phonikud | CC BY 4.0 | permissive, attribution required |
| `browser` | playwright | Apache-2.0 | test-only |

`torch` arrives transitively with stanza and sentence-transformers; its metadata reports
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
did not earn.

The biblical half never needed a model at all: the Tanakh is looked up in the Open
Scriptures morphology, CC BY 4.0, hand-tagged.

This is the honest state of the supply chain.

## Content is not code

Nothing above covers what targum *reads*. A text, a translation and a recording each
carry their own licence, held per source and shown to the reader: the foot of a reader
credits whoever read it and links the licence it came under. Library content is not in
this repository and is not covered by the AGPL.

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
