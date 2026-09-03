# targum

## The design guidelines are binding

`design.md` at the root of this repository governs every visible surface. It is not
advisory and it is not a starting point to riff on. **Read it before changing anything
visual.**

It replaced `Design updated.pdf` on 2026-08-29 as the authority. The PDF is still in the
private vault (`Project Planning/Targum internal docs/`) and still worth opening for the
drawings — the mark at four sizes, the lockups, the type specimens — but where the two
disagree `design.md` wins, and `design.md` is the one to edit. It lives here because a
document the tools cannot edit is a document that goes quietly out of date while still
being called binding, which is exactly what happened to the PDF in three places. A
reference to `Design.pdf` anywhere is stale twice over.

`tests/test_brand.py` enforces the machine-checkable half — palette, radii, type scale,
focus colour, no emoji, lowercase name, no exclamation marks, no gamification, motion
always optional. **When a brand test fails, the code is wrong, not the test.** Change the
test only when `design.md` changes first.

§12 records where the code knowingly departs from the original document: the knowledge
ramp climbs to leaf rather than gold, the Hebrew reading faces are carried rather than
named, and the voice is terser than "reasons given". Each has a date and a reason. Do not
correct them back.

## Checks

`uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
— all four, as CI runs them. Note `.venv/bin/*` shebangs are stale on this machine, so
`.venv/bin/python -m pytest` works where `uv run pytest` may not.

## The API key is in `.env`, and nothing loads it for you

`ANTHROPIC_API_KEY` lives in `.env` (gitignored, never committed). Neither `uv run` nor
`.venv/bin/python` reads it, so anything that talks to the model needs:

```
set -a && . ./.env && set +a && .venv/bin/python ...
```

Without it the failure is `Could not resolve authentication method`, which reads like a
missing key rather than an unloaded one — and the honest conclusion "there is no key" is
wrong. There is; it is just not in the environment of a fresh shell.

## Two things that are easy to get wrong

- **Do not bump `SCHEMA_VERSION`** to invalidate one stage. It feeds the cache key for
  every stage, so it forces paid re-translation of every text. To make a new word-level
  feature reach existing readers, change the annotator's name instead — that costs no
  money, because the annotator runs locally.
- **An annotator rename is free of spend but not of time.** The name is the cache key, so
  renaming it re-annotates every text by design. That was unremarkable under Stanza. Since
  the DICTA swap the annotator is a BERT model on a box with no GPU: measured on
  2026-09-03, ~1 text per minute over 158 texts — a two-hour `targum rebuild --words`
  inside `deploy.sh`, which OOM-killed twice before the box had a swapfile. Treat a rename
  as a scheduled operation rather than a side effect of a deploy, and do not rename twice
  in one release: the second rename only re-does the first one's work.
- **Readers must fetch nothing.** No script, stylesheet, font or image from the network.
  Outbound links a reader chooses to click are the one exception, and `test_render.py`
  pins the allowlist.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
