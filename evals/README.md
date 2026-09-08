# evals

`ledger.jsonl` is where a score goes so the next one can be compared with it
(targum-internal#163; `src/targum/evals.py` reads and appends it). One row per number:
the date, the stage, the system and its version, a metric, a score, and how many items
it was measured over. Appended, never rewritten; the same version twice is the
determinism check.

The stages, and what writes them:

| stage | metric | script |
| --- | --- | --- |
| `lemma` | lemma accuracy against the IAHLT treebanks | `scripts/score_annotation.py` |
| `vocalize` | `letter_vowel`, `letter_dagesh`, `shin_dot`, `qamats_qatan_recall`, `word_exact` and `skeleton_kept`, Nakdimon and DICTA's menaked on two held-out sets: `dicta-modern`, the Wikipedia third of DICTA's diacritization test corpora, and `ben-yehuda`, 26 pointed works by 12 authors from Project Ben-Yehuda's dump, none of them in Nakdimon's training set | `scripts/measure_pointing.py` (targum-internal#148) |
| `grading` | `outside_share`, the share of the chat's content lemmas outside the list it was given; `unpaired_lines` | `scripts/eval_grading.py` (targum-internal#213, #220) |
| `recast` | `judge_ok_share`, `lemma_overlap`, `unpaired`, the chat's `> ` line against a person's rendering of the same English: `corpus=tatoeba`, volunteers' sentences, `corpus=flores-plus`, FLORES+'s professional renderings (`--reference flores`), or `corpus=ntrex-128`, the WMT 2019 news set's (`--reference ntrex`) | `scripts/eval_recast.py` (targum-internal#219, #221, #222) |
| `ask` | `span_found_share`, `token_f1`, `unanswered`, the chat's reply to a question about a paragraph on a stubbed page against the span a person marked as the answer, on HeQ (`corpus=heq`) | `scripts/eval_ask.py` (targum-internal#223) |

Every chat eval spends model calls and caches nothing: the question is what the model does
today. Load the key first (`set -a && . ./.env && set +a`).

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

