# Contributing to targum

Thank you for looking. Two things to read before you open a pull request: how to sign
your work, and what signing it means for the licence.

## Sign your work

targum uses the [Developer Certificate of Origin](DCO). It is not a copyright
assignment and it is not a form to fill in — it is one line at the end of each commit
message certifying that you wrote the change, or that you have the right to contribute
it:

```
Signed-off-by: Your Name <your.email@example.com>
```

`git commit -s` adds it for you. Use your real name and an address that reaches you.
A pull request whose commits are not signed off cannot be merged, and the fix is a
rebase rather than a new pull request.

## What signing also grants

The DCO on its own says a contribution arrives under the project's licence and no
other. targum needs slightly more than that, and it is fairer to say so on this page
than to discover it later.

By signing off on a contribution you also grant David Langellotti a perpetual,
worldwide, non-exclusive, royalty-free, irrevocable licence to use, reproduce, modify,
distribute and **sublicense** your contribution, including the right to distribute it
under terms other than the AGPL.

The reason, stated plainly rather than dressed up: targum is one person's project and
the hosted service may one day need a licence the AGPL cannot express — a commercial
tier, a dataset released under different terms, a partner who cannot take AGPL code.
Without this grant, a single merged pull request would freeze the licence permanently,
and the honest consequence of that is that outside contributions could not be accepted
at all. This clause exists so they can be.

What it does **not** do: it does not take your copyright, it does not stop you using
your own work anywhere you like, and it does not remove the AGPL from anything already
released. Every version of targum published under the AGPL stays under the AGPL,
irrevocably, including the one you contributed to.

If that trade is not one you want to make, please open an issue instead of a pull
request. A described bug is a real contribution and it costs you nothing.


## Correcting a meaning, and what that grants

Decided 2026-09-22 (targum-internal#164). This is the sentence a reader agrees to, once,
before targum offers them a way to say that a word's meaning is wrong.

A correction is a judgement about Hebrew: this word, in this sentence, means that. It is
the one thing no model and no general reading app has, and it is worth saying plainly
what happens to it rather than letting somebody find out later.

By offering a correction you grant David Langellotti a perpetual, worldwide,
non-exclusive, royalty-free, irrevocable licence to use, reproduce, modify, distribute
and **sublicense** that correction, for any purpose, including a commercial one and
including training a model.

**You keep your copyright and every other right in it.** The grant is a licence and not
an assignment: you may use your own correction anywhere you like, for anything, for ever.
Nothing here is exclusive.

**Why a licence rather than the public domain.** CC0 would be cleaner for a corpus and it
was the first proposal on that card. It was not taken, because the corrections are the
part of targum that is genuinely its own, and placing them in the public domain gives
them away to everyone including whoever would otherwise pay for them. A licence keeps
them targum's to decide about, and keeps them yours as well.

**What is recorded with it.** The word, the sentence you saw it in, what the meaning said
before and what it says after, and which text you were reading. Not your name and not
your account: corrections are stored under a *role* — reader, editor, author — beside a
pseudonym that distinguishes one judge from another without identifying either. The
pseudonym cannot be turned back into an account without a secret that never leaves the
server, and it is not derivable from anything published.

**It outlives your account, and that is the point of the grant.** Corrections are not
personal data about you; they are evidence about a language, and a corpus that emptied
whenever somebody left would not be a corpus. When an account closes, the account and
everything personal in it goes — and the link between you and the pseudonym goes with it,
so what remains cannot be traced back. The Data Retention Schedule says this too.

**If you would rather not.** Then do not accept the grant. targum will not show you the
correction control, and nothing else about the product changes: you can read, mark words,
ask about a line and look up a meaning exactly as before. A reader who never corrects
anything is not a lesser reader.

> This page is written by a working developer, not a lawyer, and it has not been
> reviewed by one. If your employer's policy turns on the exact wording, ask them
> before you sign off.

## Before you open a pull request

- `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
  — all four, as CI runs them.
- `design.md` governs every visible surface, and `tests/test_brand.py` enforces the half
  a machine can check. When a brand test fails, the code is wrong, not the test.
- Readers must fetch nothing from the network. `tests/test_render.py` pins the allowlist.
- Do not bump `SCHEMA_VERSION` to invalidate one stage. It keys the cache for every
  stage, so it forces paid re-translation of every text. To make a new word-level
  feature reach existing readers, change the annotator's name instead.

## Third-party models

Some of what targum runs is not as freely licensed as targum itself. `LICENSING.md`
lists what, and what it means for you. If you are adding a dependency that ships or
downloads model weights, put its licence in that table in the same pull request.
