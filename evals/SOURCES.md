# Sources

Every set a number in `ledger.jsonl` is scored against, where it came from, and what it
may be used for (targum-internal#351). A number can only be checked again a year from now
if the set behind it can be found again, and this file is where to look.

The data itself is never committed. Each set lives on the machine that fetched or built
it, mostly in the gold directory, `<model dir>/gold` (`~/.cache/targum/models/gold`, or
under `TARGUM_MODEL_DIR`; `paths.model_dir`). What is here is how to get it again.

A reference is one of four kinds, and the kind says what a score against it can mean:

- **human-written**: a person wrote the answer, such as a translation or a span.
- **human-marked**: a person marked something on a text, such as a lemma, a vowel point
  or a word onset.
- **machine-produced**: the answer was made by a model. A score against it measures
  agreement with that model, not correctness. It is a floor against collapse.
- **no reference**: nothing to compare with. The number is a property of the output,
  measured without gold.

Licences are quoted as the source or the code states them. "Not stated" means nobody has
found one, and is not read as free.

## Summary

| set | reference kind | licence | use | ledger `stage/corpus` |
| --- | --- | --- | --- | --- |
| IAHLT treebanks | human-marked | CC BY-SA 4.0 | eval only | `lemma/iahltwiki`, `iahltknesset` |
| UD French GSD, dev | human-marked | CC BY-SA 4.0 | eval only | `lemma/ud-fr-gsd`, `ud-fr-gsd-curly` |
| UD Russian SynTagRus, dev | human-marked | CC BY-NC-SA 4.0 | eval only | `lemma/ud-ru-syntagrus` |
| UD Italian ISDT, dev | human-marked | CC BY-NC-SA 3.0 | eval only | `lemma/ud-it-isdt`, `ud-it-isdt-curly` |
| UD Yiddish YiTB, dev | human-marked | CC BY-SA 4.0 | eval only | `lemma/ud-yi-yitb` |
| DICTA modern test corpus | human-marked | public domain (README) | eval only | `vocalize/dicta-modern` |
| Project Ben-Yehuda, 26 works | pointed editions; how the points were made is not stated | public domain (LICENSE) | eval only | `vocalize/ben-yehuda` |
| Scene corrections | human-marked (settled words only) | targum's own, private | eval only, never shipped | `vocalize/scene-corrections` |
| Tanakh accents (WLC via OSHB) | human-marked | WLC public domain; OSHB CC BY 4.0 | may ship (the shelf reads it) | `stress/tanakh-taamim` |
| Wiktionary Russian examples | human-marked | CC BY-SA 4.0 and GFDL | eval only | `stress/wiktionary-ru` |
| PocketTorah word onsets | human-marked | not stated | eval only | `align/pockettorah` |
| HeQ | human-written | CC BY 4.0 | eval only | `ask/heq` |
| NTREX-128 | human-written | CC BY-SA 4.0 | eval only | `recast/ntrex-128`, `ntrex-128-ru`, `ntrex-128-in-fr`, `ntrex-128-in-ru` |
| FLORES+ | human-written | CC BY-SA 4.0 | eval only | `recast/flores-plus` (no rows yet) |
| FLORES-200 | human-written | CC BY-SA 4.0 | eval only | `recast/flores-200` (no rows yet) |
| Tatoeba pool | human-written | CC BY 2.0 FR | eval, and prompt exemplars on the box | `recast/tatoeba`, `tatoeba-ru`, `chat/tatoeba-correct`, openers for `grading/` |
| Synthetic reader, fixed openers | no reference | targum's own | eval | `grading/` (empty corpus) |
| Stored reader lines | no reference | private store | eval, never committed | `grading/stored-38` |
| Scratch shelf of six | no reference | per text on the shelf | eval | `suggest/shelf-6` |
| Morphalou 3.1, over the French shelf | no reference (coverage of a lexicon) | LGPL-LR | lookup; the French card reads it | none: no stage fits, so the number is in targum-internal#266 |
| French liaisons and readings, drafted | **model-drafted, not yet read by a person** | the texts public domain; the labels targum's own | eval only | `said/pd-fr-drafted` |

No fetch below pins a commit or a checksum except where it says so. Most read the
default branch of a repository or a live dump, so the files can change under the same
command. Where a number has to be re-checked exactly, keep the fetched file.

**Since 2026-09-27 every row a script writes carries the fingerprint of the files it was
scored against**, as `gold=<12 hex>` at the end of its note (targum-internal#351; rows
written before then have none, and were not rewritten). The fingerprint is the first 12
hex of a sha256 (`evals.fingerprint`): for one file, the file's own, so
`shasum -a 256 <file> | cut -c1-12` re-checks it; for several, a sha256 over their
`<sha256>  <name>` lines sorted by name. To check a number against a set on disk, run
`targum evals --fingerprint <file> [--fingerprint <file> …]` over the files below and
compare. A different fingerprint means different bytes: the same command fetched a
different set, and the two numbers are not measured on the same thing.

| ledger `stage/corpus` | files fingerprinted |
| --- | --- |
| `lemma/iahlt*` | `<model dir>/gold/{corpus}-{split}.conllu` for the splits scored, via the scorecard's `gold.fingerprints` |
| `lemma/ud-*` | `<model dir>/ud/<corpus>-dev.conllu` (the `-curly` rows pin the same file) |
| `vocalize/dicta-modern` | `<model dir>/gold/dicta-diacritization-modern.txt` |
| `vocalize/ben-yehuda` | the 26 files in `<model dir>/gold/ben-yehuda/` named by `BEN_YEHUDA_WORKS` |
| `vocalize/scene-corrections` | `<model dir>/gold/scene-nikkud.jsonl` |
| `stress/tanakh-taamim` | `<model dir>/oshb/<book>.json` for the books scored (the converted files, not the XML) |
| `stress/wiktionary-ru` | `<model dir>/wiktionary-ru/stressed-sentences.jsonl` (the kept sentences, not Kaikki's dump) |
| `align/pockettorah` | `aliyah.json`, each measured aliyah's book JSON and `labels/<aliyah>.txt`, under `~/.targum/evals/align/pockettorah` |
| `align/clips-*` | the release's `<split>.tsv` |
| `ask/heq` | `<model dir>/gold/heq-<split>.json` |
| `recast/ntrex-128*` | `<model dir>/gold/ntrex-<source>.txt` and `ntrex-<reference>.txt` |
| `recast/flores-plus` | `<model dir>/gold/flores-<split>-{en,he}.jsonl` |
| `recast/flores-200*` | `<model dir>/gold/flores200-<split>-{en,<lang>}.txt` |
| `recast/tatoeba*` | the pool named by `--pool` |
| `chat/tatoeba-correct` | the pool read (`--pool`, else `chat/exemplars.pool_path()`) |
| `said/pd-fr-drafted` | `evals/french-said-gold.jsonl` (in the repository) |
| `grading/` with `--pool` | the pool the openers were drawn from; without it there is no reference, and no pin |

`suggest/shelf-*` and `align/tts-*` have no reference file, so their rows carry no pin.

## IAHLT treebanks

`UD_Hebrew-IAHLTwiki` (about 5,000 Wikipedia sentences) and `UD_Hebrew-IAHLTknesset`
(about 2,800 from the Knesset record), with the lemma, part of speech and binyan of every
word tagged by people.

- **Kind:** human-marked.
- **From:** `https://raw.githubusercontent.com/UniversalDependencies/UD_Hebrew-{IAHLTwiki,IAHLTknesset}/master/he_{corpus}-ud-{split}.conllu`,
  branch `master`, not pinned (`annotate/gold.py:44`). Splits `dev` and `test` by default.
- **Licence:** "CC BY-SA 4.0" (`annotate/gold.py:42`; LICENSING.md, "The treebanks the
  annotator is scored against").
- **Fetch:** `targum models fetch gold` (`annotate/gold.py:fetch`), to
  `<model dir>/gold/{iahltwiki,iahltknesset}-{dev,test}.conllu`.
- **Use:** evaluation only. Never trained on, never read by a build, nothing derived ships.
- **Scored by:** `scripts/score_annotation.py` (the annotator), `scripts/score_dictionary.py`
  (the paid dictionary stage).
- **Ledger:** `lemma/iahltwiki`, `iahltknesset`, first on 2026-09-28 over the dev split.
  `score_annotation.py` writes a JSON scorecard, and `targum evals --record` imports one
  as `stage=lemma` rows (`evals.rows_from_scorecard`).

## Universal Dependencies dev sets

The dev split of one treebank per language, used to score the model's dictionary forms,
parts of speech and grammar features for French, Russian, Italian and Yiddish. The
`-curly` corpora are the same French and Italian sentences with every ' turned into ’ by
the script (`--curly`), not a separate download.

| corpus | file | licence |
| --- | --- | --- |
| `ud-fr-gsd` | `UD_French-GSD/master/fr_gsd-ud-dev.conllu` | CC BY-SA 4.0 |
| `ud-ru-syntagrus` | `UD_Russian-SynTagRus/master/ru_syntagrus-ud-dev.conllu` | CC BY-NC-SA 4.0 |
| `ud-it-isdt` | `UD_Italian-ISDT/master/it_isdt-ud-dev.conllu` | CC BY-NC-SA 3.0 |
| `ud-yi-yitb` | `UD_Yiddish-YiTB/master/yi_yitb-ud-dev.conllu` | CC BY-SA 4.0 |

- **Kind:** human-marked.
- **From:** `https://raw.githubusercontent.com/UniversalDependencies/<file>`, branch
  `master`, not pinned (`scripts/eval_lemma.py:69`, `TREEBANKS`).
- **Licence:** as in the table, from LICENSING.md ("The Universal Dependencies dev sets …").
  The script itself says only "CC BY-SA or CC BY-NC-SA".
- **Fetch:** on first run of `scripts/eval_lemma.py` (`fetch`, line 118), to
  `<model dir>/ud/<corpus>-dev.conllu`. No token.
- **Use:** evaluation only, on a developer's machine. Two are NonCommercial; LICENSING.md
  holds that evaluation on a laptop produces no derivative and is not commercial use.
  SynTagRus stays evaluation only under the Russian carve-out of 2026-09-27.
- **Scored by:** `scripts/eval_lemma.py` (systems `model-lemma`, and `ru-local` for the
  Russian reader that runs on the machine).
- **Ledger:** `lemma/ud-fr-gsd`, `ud-fr-gsd-curly`, `ud-ru-syntagrus`, `ud-it-isdt`,
  `ud-it-isdt-curly`, `ud-yi-yitb`.

## DICTA modern test corpus

The modern third of DICTA's Hebrew diacritization test sets: a random selection of Hebrew
Wikipedia articles, fully pointed. The rabbinic and poetry thirds are not used.

- **Kind:** human-marked. DICTA's paper describing the set: "We evaluated the system on a
  6,000-word unseen gold-test corpus, manually diacritized by a professional linguist …
  The corpus consists of a random selection of Hebrew wiki articles. We have made the test
  corpus publicly available." (Shmidman et al., "Nakdan: Professional Hebrew
  Diacritizer", ACL 2020 system demonstrations, §6.) The repository README says only "The
  files are fully diacritized Hebrew texts". targum-internal#351 calls this a machine
  corpus; the source does not support that.
- **Caveat:** it is DICTA's own house style, and DICTA's menaked is one of the two systems
  scored on it. That is why Ben-Yehuda stands beside it.
- **From:** `https://raw.githubusercontent.com/Dicta-Israel-Center-for-Text-Analysis/hebrew-diacritization-test-corpora/master/ModernTestCorpus-HebrewWiki1.txt`,
  branch `master`, not pinned (`scripts/measure_pointing.py`, `DICTA_SOURCE`).
- **Licence:** "We offer up to the public domain 3 test sets for Hebrew diacritization"
  (README). No LICENSE file.
- **Fetch:** on first run of `scripts/measure_pointing.py --corpus dicta-modern`
  (`fetch_dicta`), to `<model dir>/gold/dicta-diacritization-modern.txt`.
- **Use:** evaluation only.
- **Scored by:** `scripts/measure_pointing.py`.
- **Ledger:** `vocalize/dicta-modern`.

## Project Ben-Yehuda, 26 pointed works

Prose and poetry by 12 authors, 1880 to 1940, none of them in Nakdimon's training set.
Only fully pointed paragraphs are kept, joined into lines of 20 words or more, at most 30
lines a work.

- **Kind:** pointed text from the editions in the dump. Neither the dump's README nor its
  LICENSE says how the points were made, so whether each work's pointing is the printed
  edition's, a volunteer's or a tool's is unknown.
- **From:** `https://raw.githubusercontent.com/projectbenyehuda/public_domain_dump/master/txt/{path}.txt`,
  branch `master`. The list of works is pinned in `BEN_YEHUDA_WORKS`
  (`scripts/measure_pointing.py`), chosen 2026-09-07; the file contents are not.
- **Licence:** "The data files in this repository are in the public domain, so you are
  free to make any use of them" (the dump's LICENSE). Credit asked for, not required, to
  "Project Ben-Yehuda volunteers".
- **Fetch:** on first run of `scripts/measure_pointing.py --corpus ben-yehuda`
  (`fetch_ben_yehuda`), to `<model dir>/gold/ben-yehuda/`.
- **Use:** evaluation only.
- **Scored by:** `scripts/measure_pointing.py`.
- **Ledger:** `vocalize/ben-yehuda`.

## Scene corrections

The only nikkud set targum marked itself, pointed the way its scenes are. It is built
from the correction store: 391 Hebrew corrections with `stage="scene"` and
`who="author"`, which David settled on 2026-09-22 from two independent Opus 5 readings of
the hundred scenes (targum#396). A gold line is the line with every settled correction
applied. On 2026-09-27 that made 345 lines and 389 settled words (338 `points`, 41
`letters`, 10 `kept`). 16 corrections on 9 lines could not be placed in the line they
carry (two settlements of one word, a correction quoting part of a word, or a line quoted
after an earlier fix), and those lines are left out whole; the cast rename has no line.

- **Kind:** human-marked, for the settled words only: points changed (`points`), letters
  changed (`letters`), or a correction looked at and turned down (`kept`). The rest of
  each line passed two model readings with nothing found and was not marked word by word
  by a person. The `settled_*` metrics are the hand-marked number; the whole-line metrics
  are not.
- **Caveat:** the scenes put a holam or shuruk on the vav, and the menaked puts it on the
  letter before; `*_folded` metrics read the two as one (`measure_pointing._fold_word`).
  The scenes never write the qamats qatan, so the menaked's `qamats_qatan_precision` of 0
  here is a convention, not an error count. And a pointer cannot know who a line is
  addressed to, so a feminine "you" settled by a person is often pointed masculine.
- **From:** the local store, `~/.targum/targum.db` by default, opened read-only.
- **Licence:** targum's own content.
- **Build:** `PYTHONPATH=src .venv/bin/python scripts/scene_nikkud_gold.py`, to
  `<model dir>/gold/scene-nikkud.jsonl`. Not fetched; rebuilt from the store at any time.
- **Use:** private. Never committed, never shipped, never trained on. Exists only on the
  owner's laptop.
- **Scored by:** `scripts/measure_pointing.py --corpus scene-corrections`.
- **Ledger:** `vocalize/scene-corrections`.

## Tanakh accents

Words of six prose books (Genesis, Exodus, Deuteronomy, 1 Samuel, Isaiah, Jeremiah) that
carry one placed Masoretic accent. The accent sits on the stressed syllable, so taking it
off and asking where the stress falls has an answer on the page (`pronounce.stressed`).

- **Kind:** human-marked: the Masoretes' accents, as the Westminster Leningrad Codex
  encodes them.
- **From:** `https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/{book}.xml`,
  branch `master`, not pinned (`annotate/oshb.py:43`).
- **Licence:** the text is the Westminster Leningrad Codex, public domain; the
  morphology is the Open Scriptures Hebrew Bible Project's, "CC BY 4.0"
  (`annotate/oshb.py:57`; LICENSING.md, "The Hebrew Bible is read, not analysed").
- **Fetch:** `targum models fetch scripture` (`oshb.fetch`), to `<model dir>/oshb`.
- **Use:** not evaluation-only data. The shelf reads the same files to annotate
  scripture, and the credit ships with it.
- **Scored by:** `scripts/eval_hebrew_stress.py`. `--baseline-only` needs no key; a model
  run sends the unaccented words to a paid endpoint.
- **Ledger:** `stress/tanakh-taamim`.

## Wiktionary Russian examples

Usage examples and quotations from English Wiktionary's Russian entries, which print every
stress. Only fully stressed sentences of six words or more are kept.

- **Kind:** human-marked. Caveat from the script: OpenRussian's tables were built from
  Wiktionary too, so the rule's `stress_precision` is not independent of this gold;
  `silero_precision` is.
- **From:** Kaikki.org's extraction,
  `https://kaikki.org/dictionary/Russian/kaikki.org-dictionary-Russian.jsonl`, the live
  file, not pinned (`scripts/eval_stress.py:54`).
- **Licence:** "Wiktionary's text is CC BY-SA 4.0 and GFDL" (`scripts/eval_stress.py:8`).
- **Fetch:** on first run of `scripts/eval_stress.py` (`fetch`, line 79), streaming the
  900 MB file once, to `<model dir>/wiktionary-ru/stressed-sentences.jsonl`.
- **Use:** evaluation only.
- **Scored by:** `scripts/eval_stress.py`.
- **Ledger:** `stress/wiktionary-ru`.

## PocketTorah word onsets

For six aliyot (Bereshit-1, Noach-2, Shemot-2, Vayikra-1, Bamidbar-1, Devarim-1), the
second at which each chanted word begins, marked by hand in an audio editor for the
PocketTorah app. The script notes the marks run 200 to 420 ms ahead of the voice, as a
follow-along app would want.

- **Kind:** human-marked.
- **From:** `https://raw.githubusercontent.com/rneiss/PocketTorah/master/data`: the label
  files under `torah/labels/`, the word lists under `torah/json/`, and `aliyah.json`.
  Branch `master`, not pinned (`scripts/eval_align.py:211`). The audio is the
  `PockettorahAudioFiles` collection on archive.org, already on disk for the leyning
  (`parasha/leyning.py:49`).
- **Licence:** labels not stated; the repository has no licence file. The audio is
  "CC BY-SA 3.0" (`parasha/leyning.py:54`).
- **Fetch:** on first run of `scripts/eval_align.py --on pockettorah`, to
  `~/.targum/evals/align/pockettorah` (`scripts/eval_align.py:459`).
- **Use:** evaluation only. Never committed, never trained on, never shipped.
- **Scored by:** `scripts/eval_align.py --on pockettorah`.
- **Ledger:** `align/pockettorah`.

## HeQ

30,147 reading-comprehension questions over 4,401 paragraphs of Hebrew Wikipedia and
Geektime, each answered by a person with the span that answers it. Annotated by Webiks
for MAFAT under the National NLP Plan of Israel.

- **Kind:** human-written.
- **From:** `https://raw.githubusercontent.com/NNLP-IL/Hebrew-Question-Answering-Dataset/main/data/data%20v1.1/{val,test} v1.1.json`,
  branch `main`, file version v1.1 (`chat/heq.py:35`).
- **Licence:** "CC BY 4.0" (`chat/heq.py:33`).
- **Fetch:** `targum models fetch heq` (`chat/heq.py:fetch`), to
  `<model dir>/gold/heq-{val,test}.json`. The eval draws from `test`.
- **Use:** evaluation only, though the licence would permit more.
- **Scored by:** `scripts/eval_ask.py`.
- **Ledger:** `ask/heq`.

## NTREX-128

The WMT 2019 news test set: 1,997 English source sentences, each rendered by a
professional translator into 128 languages. Every reference renders the same source line
by line, which is what lets a Russian line be scored against the Hebrew for it.

- **Kind:** human-written.
- **From:** `https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128/{file}`,
  branch `main`, not pinned (`chat/ntrex.py:37`). Files `newstest2019-src.eng.txt`,
  `newstest2019-ref.heb.txt`, `newstest2019-ref.rus.txt`, `newstest2019-ref.fra.txt`.
- **Licence:** "CC BY-SA 4.0" (`chat/ntrex.py:35`).
- **Fetch:** `targum models fetch ntrex` (`chat/ntrex.py:fetch`), to
  `<model dir>/gold/ntrex-{en,he,ru,fr}.txt`. No token.
- **Use:** evaluation only.
- **Scored by:** `scripts/eval_recast.py --reference ntrex`.
- **Ledger:** `recast/ntrex-128` (English turn, Hebrew reference), `ntrex-128-ru` (Russian
  turn, Hebrew reference), `ntrex-128-in-fr` and `ntrex-128-in-ru` (English turn, French
  or Russian reference) (`scripts/eval_recast.py:corpus_of`).

## FLORES+

2,009 English sentences from 842 web articles, each rendered into Hebrew by a
professional translator. The eval uses `devtest` (1,012).

- **Kind:** human-written.
- **From:** Hugging Face dataset `openlanguagedata/flores_plus`,
  `resolve/main/{split}/{eng_Latn,heb_Hebr}.jsonl`, revision `main`, not pinned
  (`chat/flores.py:37`).
- **Licence:** "CC BY-SA 4.0" (`chat/flores.py:36`). Gated: the conditions must be
  accepted on the dataset page.
- **Fetch:** `targum models fetch flores` (`chat/flores.py:fetch`) with a read token in
  `HF_TOKEN` (or `HUGGINGFACE_HUB_TOKEN`), to `<model dir>/gold/flores-{split}-{en,he}.jsonl`.
- **Use:** evaluation only.
- **Scored by:** `scripts/eval_recast.py --reference flores`.
- **Ledger:** `recast/flores-plus`. No rows yet.

## FLORES-200

Meta's archived release that FLORES+ continues, fetched because it needs no token and
carries Yiddish (`ydd_Hebr`), which NTREX-128 does not. A number here is comparable to
published FLORES-200 numbers and only approximately to FLORES+ ones.

- **Kind:** human-written.
- **From:** `https://tinyurl.com/flores200dataset`, the redirect the dataset card gives,
  followed to a tarball; not pinned (`chat/flores200.py:50`).
- **Licence:** "CC BY-SA 4.0" (`chat/flores200.py:46`).
- **Fetch:** `targum models fetch flores200 --language <yi|he|fr|ru>`
  (`chat/flores200.py:fetch`), to `<model dir>/gold/flores200-{split}-{lang}.txt`.
- **Use:** evaluation only.
- **Scored by:** `scripts/eval_recast.py --reference flores200`.
- **Ledger:** `recast/flores-200`, with `-in-<lang>` for another target. No rows yet.

## Tatoeba pool

Hebrew sentences from Tatoeba whose contributor declares Hebrew native, not reviewed as
wrong, each linked to an English sentence: 165,454 rows on 2026-09-07, three contributors
writing 96% of them. 6,682 rows carry a Russian sentence from Tatoeba's `heb-rus` links.

- **Kind:** human-written, by volunteers. For `tatoeba-correct` the Hebrew is sent as the
  reader's line and assumed correct because a native speaker wrote it; that metric counts
  a property of the reply (a `~ ` line on a correct line), not a match with a reference.
- **From:** the exports at `https://tatoeba.org/en/downloads` (`heb_sentences_detailed.tsv`,
  `eng_sentences_detailed.tsv`, `links.csv`, `sentences_base.csv`, `user_languages.csv`,
  `users_sentences.csv`) and, for Russian, `https://downloads.tatoeba.org/exports/per_language/`
  (`heb-rus_links.tsv`, `rus_sentences_detailed.tsv`). The exports are undated and not pinned.
- **Licence:** "CC BY 2.0 FR, per sentence, per contributor" (`scripts/tatoeba_pool.py`
  docstring; LICENSING.md, "Tatoeba's sentences"). Every row keeps each contributor's
  username. Tatoeba's audio is not taken.
- **Build:** `scripts/tatoeba_pool.py --exports <dir> --out ~/.targum/exemplars.jsonl`, then
  `scripts/tatoeba_russian.py --exports <dir> --pool ~/.targum/exemplars.jsonl --out ~/.targum/exemplars-ru.jsonl`.
  The chat reads the pool from `TARGUM_EXEMPLARS`, else `~/.targum/exemplars.jsonl` or
  `/etc/targum/exemplars.jsonl` (`chat/exemplars.py`).
- **Use:** the one reference set that also reaches production: the same pool is the
  chat's prompt exemplars on the box. Never in the repository or the wheel, never on a
  page, never trained on. The recast eval removes its own rows from the exemplars it
  rides (`scripts/eval_recast.py`).
- **Scored by:** `scripts/eval_recast.py` (default reference), `scripts/eval_why.py`,
  and `scripts/eval_grading.py --pool` for openers.
- **Ledger:** `recast/tatoeba`, `recast/tatoeba-ru`, `chat/tatoeba-correct`; `grading/`
  rows whose note says `openers=tatoeba`.

## Morphalou 3.1, over the French shelf

The share of the French shelf's word tokens that Morphalou gives a transcription for,
counted before the French pronunciation card is built (targum-internal#266). Not a score:
nothing is compared with a reference, and no stage in `ledger.jsonl` measures a lexicon's
reach, so the number is recorded in the issue and the PR rather than in the ledger.

- **Kind:** no reference. The number is how much of the shelf a lookup reaches.
- **From:** ORTOLANG, `https://repository.ortolang.fr/api/content/morphalou/5/Morphalou3.1_formatCSV_toutEnUn.zip`,
  pinned by sha256 `4fc815cbf17aecdf1b47f6bbc263489a460fd8d11ae17e6b522336c72bd0e333`
  (`annotate/morphalou.py`). No account is needed.
- **Licence:** "Morphalou3 est distribué sous licence LGPL-LR" (the table's own header);
  the licence text is at the end of `LICENSING.md`.
- **Fetch:** `targum models fetch morphalou`, to `<model dir>/morphalou/3.1/Morphalou3.1_CSV.csv`
  and `licenceLGPLLR.txt` beside it.
- **Use:** a lookup, never trained on, never committed.
- **Counted by:** `scripts/measure_pronunciation.py`, over the catalogue's French texts:
  the reader's own tokens where a text is built on the machine, and otherwise the text
  fetched from its source and split by the rules the French annotator is given.
- **Ledger:** none.

## French liaisons and readings, drafted

The gold the French card's liaisons and readings are scored against (targum-internal#266):
342 sentences of four public-domain texts on the French shelf — Perrault's *Le Petit
Chaperon rouge* (1826 edition), Daudet's *La Chèvre de monsieur Seguin*, Maupassant's *La
Folle* and Allais's *Un philosophe* — as Wikisource gives them (`ingest.load`), split
into sentences.

- **Kind: model-drafted, and not yet read by a person.** The issue asks for a set written
  by hand; this one was drafted by three model passes, on 2026-09-28, and says so on every
  row (`"drafted"`). Each sentence's words, dictionary forms, parts of speech and features
  were drafted following the tagger's own instruction (`model_lemma.SYSTEM`) and placed
  by the tagger's own parser. Each place a liaison could be made — a word ending in a
  consonant letter before a word beginning with a vowel, h or y, with nothing but a
  space or a hyphen between — was labelled `always`, `optional` or `never`, with the
  consonant heard, by a pass that was not shown the rule (389 places: 124 always, 153
  optional, 112 never). The reading of each word Morphalou says two ways, that the card
  corrects or that it says by parts was chosen by a third pass (174 words). Where the
  literature splits between always and optional, the label is optional.
- **Not PFC.** The PFC corpus is NonCommercial and is not used.
- **Licence:** the texts are public domain; the labels are targum's own.
- **Where:** `evals/french-said-gold.jsonl`, in the repository.
- **Use:** evaluation only. The liaison precision is the rule's given the tags the gold
  drafted; `--tagger` runs the tagger instead, which spends.
- **Scored by:** `scripts/eval_liaison.py`.
- **Ledger:** `said/pd-fr-drafted`.

## Sets with no reference

These are measured without gold. The number is a property of the output.

- **`grading/` (empty corpus).** A synthetic word list (N common words plus the floor)
  and ten fixed openers in `scripts/eval_grading.py` (`OPENERS`), or Tatoeba openers with
  `--pool`. Measures the share of the chat's content lemmas outside the list, as read by
  the DICTA annotator. Scored by `scripts/eval_grading.py`.
- **`grading/stored-38`.** Stored model output, not a person's answer: 37 reader lines
  from `chat_turn` in the local store, replayed live through `Chats.answer` on a copy of
  the store, measuring Hebrew words per reply. Private; never committed. No script in the
  repository writes these rows; the notes on 2026-09-15 describe the runs.
  `scripts/measure_reply_length.py` reads the same store without spending.
- **`suggest/shelf-6`.** Six 19th-century novels on a scratch shared shelf, the canon this
  laptop had on 2026-09-22. Measures the `known_share` of what `suggest_next` offers a
  reader who knows the 500 commonest words. Calls no model. Scored by
  `scripts/eval_suggest.py`; the corpus name records the shelf size.
- **`eval_align.py --on tts`.** Each word synthesised as its own clip and joined, so every
  boundary is known by construction. An upper bound, not a hand-marked truth. No rows yet.
- **`eval_align.py --on clips`.** Built for Common Voice's layout; no set fetched and no
  rows yet.
