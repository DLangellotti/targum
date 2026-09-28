# evals

`ledger.jsonl` is where a score goes so the next one can be compared with it
(targum-internal#163; `src/targum/evals.py` reads and appends it). One row per number:
the date, the stage, the system and its version, a metric, a score, and how many items
it was measured over. Appended, never rewritten; the same version twice is the
determinism check.

The stages, and what writes them. Every stage and corpus in `ledger.jsonl` is here, and
nothing is here that no script writes, except where it says so:

| stage | corpus | metric | script |
| --- | --- | --- | --- |
| `lemma` | `iahltwiki`, `iahltknesset` | the annotator against the IAHLT treebanks, system `dicta/…`; the first rows are the dev split. The script writes a JSON scorecard, not rows; `targum evals --record scorecard.json` turns it into `lemma` rows | `scripts/score_annotation.py`, then `targum evals --record` |
| `lemma` | `ud-fr-gsd`, `ud-it-isdt`, `ud-ru-syntagrus`, `ud-yi-yitb`; `ud-fr-gsd-curly`, `ud-it-isdt-curly` | `token_recall`, `lemma_accuracy`, `upos_accuracy` and the grammar features (`case_`, `aspect_`, `gender_`, `number_`, `tense_`, `mood_`, `person_`, `verbform_accuracy`): the model's reading of French, Russian, Italian and Yiddish against the Universal Dependencies dev sets, system `model-lemma`, or `ru-local` for the Russian reader that runs on the machine. `-curly` is the same sentences written with ’ (`--curly`) | `scripts/eval_lemma.py` (targum-internal#258, #262) |
| `vocalize` | `dicta-modern`, `ben-yehuda`, `scene-corrections` | `letter_vowel`, `letter_dagesh`, `shin_dot`, `qamats_qatan_recall`, `qamats_qatan_precision`, `word_exact`, `skeleton_kept`, and `*_folded`, which reads a vowel beside a vav one way. Nakdimon and DICTA's menaked on `dicta-modern`, the Wikipedia third of DICTA's diacritization test corpora, and `ben-yehuda`, 26 pointed works by 12 authors, none in Nakdimon's training set; the menaked on `scene-corrections`, the scenes' lines as a person settled them (targum#396), private, with the settled words scored on their own as `settled_*` (targum-internal#351) | `scripts/measure_pointing.py` (targum-internal#148); the scene set is built by `scripts/scene_nikkud_gold.py` |
| `stress` | `wiktionary-ru` | `stress_precision`, `stress_coverage`, `yo_precision`, `yo_recall`, and `silero_precision` (system `silero-stress`, silero alone, the independent number): Russian stress marks against sentences stressed by hand in English Wiktionary's examples and quotations, evaluation only | `scripts/eval_stress.py` (targum-internal#260) |
| `stress` | `tanakh-taamim` | `default_accuracy` (system `phonikud/2`, the last syllable every time, `--baseline-only`, no key); `stress_accuracy`, `stress_precision`, `stress_coverage` for a model run, which spends: Hebrew stress against the syllable a Masoretic accent marks, in six prose books | `scripts/eval_hebrew_stress.py` (targum-internal#309) |
| `align` | `pockettorah` | `onset_ms_median`, `onset_ms_mean`, `onset_ms_lag_median`, `onset_within_100ms`, `onset_within_250ms`, `right_word_lit`: the forced aligner's word starts on chanted Torah against PocketTorah's hand-marked onsets (`--on pockettorah`). `--on tts` (`tts-<lang>`, `boundary_ms_*`, `within_50ms`) and `--on clips` (`word_in_its_clip`) write rows too; none are in the ledger yet | `scripts/eval_align.py` (targum-internal#225, #265) |
| `said` | `pd-fr-drafted` | `liaison_precision` (floor 0.98), `liaison_recall`, `ipa_word_accuracy`, `ipa_coverage`: the French card's liaisons and readings against a gold of 342 public-domain sentences, **model-drafted and not yet read by a person**, with the gold's own tags (`--tagger` runs the tagger, and spends) | `scripts/eval_liaison.py` (targum-internal#266) |
| `grading` | empty | `outside_share`, the share of the chat's content lemmas outside the list it was given; `unpaired_lines`; `hebrew_words_median`; `stray_why_lines`. Openers are fixed, or drawn from the Tatoeba pool with `--pool` (the note says `openers=tatoeba`) | `scripts/eval_grading.py` (targum-internal#213, #220) |
| `grading` | `stored-38` | `hebrew_words_median`, `hebrew_words_max`: stored reader lines replayed through the chat. No script in the repository writes these; the rows' notes describe the runs | none (`scripts/measure_reply_length.py` reads the same store without spending) |
| `recast` | `tatoeba`, `tatoeba-ru`, `flores-plus`, `flores-200`, `ntrex-128`, `ntrex-128-ru`, `ntrex-128-in-fr`, `ntrex-128-in-ru` | `judge_ok_share`, `lemma_overlap`, `unpaired`: the chat's `> ` line against a person's rendering of the same English: Tatoeba volunteers' sentences (default), FLORES+ (`--reference flores`), FLORES-200 (`--reference flores200`) or the WMT 2019 news set (`--reference ntrex`). `-ru` is a Russian turn; `-in-<lang>` is a reference in that language (`corpus_of`). No `flores-plus` or `flores-200` rows yet | `scripts/eval_recast.py` (targum-internal#219, #221, #222, #286) |
| `chat` | `tatoeba-correct` | `why_on_correct_lines`, `why_shown_on_correct_lines`: `~ ` lines the chat writes, and the reader is shown, under a correct line a native speaker wrote | `scripts/eval_why.py` (targum-internal#242) |
| `ask` | `heq` | `span_found_share`, `span_found_share_ktiv`, `token_f1`, `unanswered`: the chat's reply to a question about a paragraph on a stubbed page against the span a person marked as the answer | `scripts/eval_ask.py` (targum-internal#223) |
| `suggest` | `shelf-<n>` | `suggested_known_share`, `suggested_with_known_share`: the known share of the texts `suggest_next` offers a reader who knows the commonest words, and how many offers carry one, over the texts built on this machine. Calls no model | `scripts/eval_suggest.py` (targum-internal#244) |

`targum eval <stage>` runs any of these from the repository root, passing everything
after the stage to the script: `targum eval vocalize --corpus dicta-modern`. `lemma` and
`stress` are each measured by two scripts, so they are named by corpus:
`lemma/iahlt` and `lemma/ud`, `stress/tanakh-taamim` and `stress/wiktionary-ru`
(`evals.SCRIPTS`). `targum eval rail` runs `scripts/eval_rail.py` (targum-internal#324),
which writes no ledger row. Calling the script by path still works; the command is only
the way in.

What each corpus is, where it comes from, its licence and what it may be used for:
`SOURCES.md`. Each row a script writes now ends its note with `gold=<12 hex>`, the
fingerprint of the reference files it was scored against (targum-internal#351);
`SOURCES.md` says how to check one.

Every chat eval spends model calls and caches nothing: the question is what the model does
today. Load the keys first: prefix the command with `op run --env-file op.env --`.

## Floors

`floors.json` is where each measurement may not fall below — or, for a count of
failures, rise above — for the system the shelf actually runs. One line per floor:
the key, the system as a prefix, `at_least` or `at_most`, and a `why` that names the
number it was set from. `tests/test_evals.py` checks the committed ledger against it,
so a PR that records a worse score fails CI until the floor is moved in the same PR,
where a reviewer sees it; `targum evals --check` is the same check by hand
(targum-internal#163, criterion 5).

Floors are for a collapse, not a ranking: they sit a little under the number the
production system last scored, and a comparison run of some other system is a
measurement rather than a breach, which is why each names its system. A stage nobody
has run yet has no floor, and gets one with its first real row.

