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
| `grading` | `outside_share`, the share of the chat's content lemmas outside the list it was given; `unpaired_lines` | `scripts/eval_grading.py` (targum-internal#213, #220) |
| `recast` | `judge_ok_share`, `lemma_overlap`, `unpaired`, the chat's `> ` line against a native speaker's rendering of the same English, on Tatoeba pairs | `scripts/eval_recast.py` (targum-internal#219) |

Every chat eval spends model calls and caches nothing: the question is what the model does
today. Load the key first (`set -a && . ./.env && set +a`).
