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

**From a git worktree, point `PYTHONPATH` at that worktree's `src`.** `.venv` holds an
editable install addressing the main checkout, so a run started in a worktree imports
`targum` from the main checkout and tests code you did not edit — a browser test there
serves the unedited JS and CSS, and the dangerous version is the run that passes.
`tests/conftest.py` now refuses to start on it and prints the command, so it cannot
happen by accident; the command is

```
PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q
```

which also drops the gitignored private half from the import path, so the skips match
what CI's public checkout sees.

**And that is why the private half needs a run of its own, from the main checkout.** The
eight gitignored modules — the weekly's writer and voice, the dialogue writer, the
recording cutter and aligner — exist nowhere else: not in CI's public checkout, not in
any worktree, and **not in the wheel either** (hatchling drops VCS-ignored files; the
only one added back is `activity.json`). So no lint, no type check and no test sees them
unless you are standing in the main checkout, and a rename in the public half breaks one
of them with every check still green (targum-internal#230).

**A pre-push hook runs those checks here, so it is not something to remember.** Install
it once per clone — `.git/hooks` is not shared, and this is the only clone with a private
half to check:

```
./deploy/hooks/install.sh
```

It runs `ruff check`, `ruff format --check`, `mypy` and `tests/test_private_half.py` over
the eight, and it is silent and instant in a tree that has none of them, which is every
worktree. `git push --no-verify` skips it. To run the same checks by hand:

```
uv run ruff check src/targum && uv run mypy && .venv/bin/python -m pytest -q tests/test_private_half.py
```

`tests/test_private_half.py` imports each of the eight where it exists and skips where it
does not, so the same file is honest on both kinds of tree. It also refuses a *partly*
copied checkout, which would build a wheel with holes in it. Three lint errors were found
sitting in the private half on 2026-09-09, the first time anything looked; installing the
hook the same day found three more and a formatting divergence.

## The weekly runs itself now, from this laptop

`deploy/weekly-run.sh` does the whole chain — brief, draft, build, publish, the Russian
edition, ship, announce — and `deploy/weekly.plist.example` is the `launchd` job that runs
it on a Monday.
**Installing the plist does not arm it**; `launchctl load` does, and nothing here loads
it for you, because the job writes an issue with a model, publishes it under the targum
name and mails whoever asked for it.

It runs *here*, from the main checkout, for the reason the private half exists: the eight
gitignored modules are not in the wheel, not on the box and not in any worktree. The
script checks for `weekly/write.py` before `draft`, which is the first step that spends.

**The gate came out on 2026-09-17 and the guards did not.** Nobody reads an issue before
it goes out, so no issue claims anybody did: the byline and the notice are both off the
page, and `BYLINE_HE` survives only so issues published before the change still read as
they did. `publish` still refuses a lifted phrase (the licence boundary) and still refuses
a missed band, and the scheduled run never passes `--anyway`. A run that stops has found
something.

**Every issue has a Russian edition, and the mail goes out from the box** (both
2026-09-27). The Russian is built after `publish`, so an issue the guards refuse spends
nothing on it, and a Russian build that stops never holds back the English. `announce`
runs *on the box* after the ship, against `/var/lib/targum/targum.db`: the site's
subscribers live there, and an announce from the laptop reads the laptop's database, where
they never are (targum-internal#346). A subscription made on the laptop is not mailed.

## The keys are in 1Password, and nothing loads them for you

Every key lives in the `targum` vault in 1Password and nowhere else (targum-internal#326,
2026-09-26). `op.env` names the laptop's as `op://` references — no values, so it is
committed — and neither `uv run` nor `.venv/bin/python` reads it, so anything that talks
to a model needs:

```
op run --env-file op.env -- .venv/bin/python ...
```

Without it the failure is `Could not resolve authentication method`, which reads like a
missing key rather than an unloaded one — and the honest conclusion "there is no key" is
wrong. There is; it is just not in the environment of a fresh shell.

- **The box's keys are `deploy/box.env.op`.** `deploy.sh` resolves them before it builds
  and writes them into `/etc/targum/targum.env` on every deploy, leaving the non-secret
  settings alone. Rotating a key is: change it in the vault, deploy. A new key is a line
  in that file too, or it never reaches the box.
- **The laptop and the box hold different Anthropic and OpenAI keys** — items
  `Anthropic laptop` / `OpenAI laptop` against `Anthropic` / `OpenAI` — so a console's
  usage says which machine spent it.
- **The Monday weekly and `deploy.sh` read as the `targum-box` service account**:
  read-only, the `targum` vault only, its token in the Personal vault and, for unattended
  runs, in the login keychain. With it there, a deploy needs nobody at the fingerprint
  reader (2026-09-27); without it, `op` falls back to the app's unlock. Putting it there, once, in a terminal of your own:

  ```
  security add-generic-password -a "$USER" -s targum-op-service-account -T /usr/bin/security \
    -w "$(op item get 'Service Account Auth Token: targum-box' --vault Personal --fields credential --reveal)"
  ```

  The colon in that item's title makes it unaddressable as an `op://` reference; `op
  item get` by title is the way in.

## Things that are easy to get wrong

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
- **A chat turn never spends without a quoted, consented job**, and never routes around
  `Library.claim`. The chat is a door on rooms that exist; the model may ask
  (`quote_*`), a person presses, and only then does `start_build` run. A tool that
  spends on a model's decision makes the pricing page a lie. Every turn is a `job` row
  of kind `chat`, so the rails see it — do not invent a second counter. The one spend
  before a card is the reading of a picture brought by the `+` (2026-09-07): the file
  choice is the consent, it is capped at thirty pages, and it still goes through
  `Library.claim` and is settled to the receipt (`Library._read_pages`). And Send with
  a file in the box is the press (2026-09-07): the person chose the file and sent it,
  so the page posts `/build` itself and opens the reader when it is done — still the
  person's own hand, never the model's, and still through `Library.claim`. A line
  that says more than "open this" is said to the model with a note of what was sent;
  the model is told, and still cannot open or spend. An Instagram post's pictures are
  the same spend on the same rails (2026-09-18): its caption is read for free, and its
  pictures only when the person presses "Also read the pictures" on the card
  (`Library._prepare_post`).
- **A scope is the one press that lasts** (2026-09-22, design.md §12). Over the remote
  connector there is no page of ours to press per turn, so `record_turn` — the only tool
  that spends without a card — is consented once, by the reader ticking the `check` scope
  on targum's own approval page where the cost is said in hours, and revoked there. It is
  still a `job` row of kind `chat` through `Library.claim_turn`, still inside
  `CHAT_BUDGET` and the eight hours, and still no second counter. Everything else holds:
  a build needs its own press, the model cannot press anything, and a quote is
  information. Do not widen this to a second tool without an entry in §12 first.
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
