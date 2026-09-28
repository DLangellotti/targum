# targum — English copy voice guide

A working guide for anyone writing English inside targum or in its email. `design.md` §6 is
the authority, and §12 records the dated decisions behind it. This file turns both into
checks you can run over a line before you ship it. Where the two disagree, `design.md` wins.
Settled 2026-09-28 in the copy audit (`COPY_AUDIT.md`).

## Who we're talking to

An intelligent first-time reader who has never seen targum. They know how to use ordinary
software. They may not know "CEFR", "binyan", "aliyah", "niqqud" or what a targum is.

## The voice

- **We speak as "we", to "you".** Like a person behind a counter: "Thanks for the link.
  We're working out how long it'll take."
- **The main point comes first.** Then the next step. One idea per sentence. If a sentence
  needs a second comma, it is usually two sentences.
- **Short, not curt.** A line is one or two sentences. A button or link is one or two words.
- **Warm where something happened.** Thank people when they hand us something. Name real
  progress with real numbers ("500 words known"). Keep instructions, errors, account
  messages and time-sensitive email plain.
- **Never:** exclamation marks, emoji, "Oops", "Awesome", "Just a moment", hype, slogans,
  or the stock phrases of AI prose ("unlock", "seamless", "dive in", "journey", "Great
  question"). No XP, points, levels-as-rewards or streak guilt. Missed days are quiet.
- **The name is always lowercase: targum**, even at the start of a sentence.

## Accuracy comes before style

Before you write "saved", "sent", "ready", "we'll email you", "free" or a number, find the
code that makes it true. The audit found these five failures most often:

1. **Claims that are only true on the first visit or the current week.** "This week's",
   "today's" and "Today is the first" appear on archived and empty pages too. Say "this
   issue" and "this day's", or state the condition.
2. **"One press and you're done" when there are two presses.** The confirm emails open a
   page that asks again. Say "Press Confirm to finish joining".
3. **Naming a button that isn't there.** Quote the label exactly, or describe the action
   without quoting it.
4. **Singular plural forms.** Every `tn(... "one", "other")` needs a singular that really is
   singular: "1 word", not "1 words".
5. **Blaming the connection for a server answer.** If the server said why, show what it said.

## Errors, empty states, waits

- **Error:** what happened, owned by us, then what to do. "We couldn't open that PDF. Try
  another copy, or paste the text itself." Never "invalid", never the reader's fault,
  never a status code or an operator hint ("install yt-dlp").
- **Empty state:** why it's empty, then how to start. "No playlists yet. Use Add to
  playlist on any text to start one."
- **Wait:** what we're doing now, then when it ends, in minutes. "We're getting it ready.
  You'll find it in Your targums."
- **Link that stopped working:** "That link no longer works." Then the way to a new one. A
  link can be used up or time out, so don't say which unless the code knows.

## Buttons

- Name the action: Send a link, Remove file, Exit full screen, See usage.
- **Read / Listen / Watch** when the item is known; **Open** when it isn't (§6). Don't
  put "Start reading" over audio or video.
- A button that spends credits sits beside the credit figure.

## Money and time

- There is no price inside the product. A cost is **credits**, and **1 credit = 1 minute
  of audio or video**. Show the rate wherever a balance appears. At a cost point the
  figure alone is fine.
- A wait is a time, in minutes: "about 4 minutes".
- Chatting is **included**. Don't put a per-message cost on it.
- Don't use "free", "price", "quote" or "sale" inside the product. Say "The library still opens" or "uses no credits". Public pages may sell; see §6.
- Chatting is "included". The approval page names no allowance (§12, 2026-09-24). Only the /connect FAQ says what it is included in: "your monthly credits". Don't write "uses no credits" for chat: a chat turn is metered.

## Terminology

| Thing | Say | Don't say (to readers) |
|---|---|---|
| The product | targum (lowercase) | Targum, the app |
| The account page | **Your profile** | You, the profile page (except in the legal text) |
| Keeping a chat as a text | **Save as a text** | Save as targum |
| Leaving a mailing | **Unsubscribe** | Stop these emails |
| A text with its translation held line by line, in the reader's collection | a targum; the collection is **Your targums** | your shelf, your build |
| Everyone's catalogue | **the library** in a sentence, **Library** as the nav label and page name | the catalogue, the shelf |
| One item in the library or a playlist | a text | a doc, a book (unless it is one) |
| Making a text ready | get it ready, make it | build, built, quote |
| Talking with targum, in the app or in Claude/ChatGPT | **chat**, chatting; the list is **Chats** | conversation (except where it means a dialogue in a scene), check, turn |
| Setting a word's level | mark (just met · getting there · nearly there · known) | rate, score |
| The `m` toggle that tints unlearned words | highlight | mark |
| Words the reader has put on their list | **saved** words | kept (still used in the reader's phrase tools — see the audit) |
| The allowance | credits | hours, minutes (as a pool), balance points |
| Confirming a build or a set that Claude or ChatGPT set up | confirm it on targum | press Start, open it |
| The weekly publication | the Weekly News Digest; one issue | newsletter |
| Linking targum to Claude or ChatGPT | connect; the feature is **targum in Claude and ChatGPT** | targum Connect, the MCP, the connector (except in the host's own menus and the public foot's "Install MCP") |
| A unit of a text you read | section | chunk. (Add and the build card still say “part” for what a build makes first.) |
| A followed series | follow; the list is **Following** | subscription (kept for billing) |

Capitalise named pages as they appear in the nav: Your targums, Your Progress, Library,
Add. Otherwise use sentence case.

## Explaining terms

Explain a newcomer's term the first time they meet it, in a clause, not a glossary:
"conjugations on Pealim", "All its forms", "if you know 1,000 words". The chat model is told
to do the same for binyan and niqqud (`chat/prompts.py`).

## English beside Hebrew

- Hebrew content is content. None of these rules apply to it, and copy edits never touch it.
- A sentence that starts with a Hebrew title may be shown right-to-left, with its full stop
  on the wrong side. Put the English first, or set the title in its own `dir="rtl"` span.

## Mechanics

- English lives in `src/targum/strings/en.json` and again at the call site
  (`t("key", "English")`). `tests/test_strings.py` keeps the two equal. Change both
  together.
- Changing English makes the Russian stale, and `test_strings.py` says so. Re-read the
  Russian, fix it if the meaning changed, then stamp it (`scripts/stamp_strings.py`).
- Email English is also edited through `scripts/mail_notes.py`. After changing a `mail.*`
  key, `push --force` the notes so they don't carry the old words.
- `tests/test_brand.py` enforces the lowercase name, no exclamation marks and no emoji. The
  chat model's English rules live in `chat/prompts.py` and are held by
  `tests/test_chat_prompts.py`.
