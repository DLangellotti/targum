# Copy audit — questions for David

These are the decisions I couldn't settle from the code or `design.md`. Each one has a
recommendation. **To answer, reply "use your recommendations", or name the numbers you want
done differently** (e.g. "all yes except 7: keep Free to open; 15: skip"). Nothing in this
file has been applied yet unless it says so.

Routine editorial and terminology calls are already applied and are not here. They're
listed in `COPY_AUDIT.md`, with the terms in `COPY_VOICE_GUIDE.md`.

---

## Answers (David, 2026-09-28)

- **1:** yes. Update and stamp the 38 Russian strings.
- **2–10:** fix all of them, in a follow-up PR (not this one).
- **11–16:** use the recommendations.
- **17–19:** apply all three, including the privacy notice amendments.
- **20–23:** use the recommendations.
- **24–27:** apply all four: Following / Your profile, Save as a text, one connector
  name, and "Sign in to targum" as the heading.
- **28–30:** use the recommendations.

---

## A. Blocking the merge

**1. May I update 38 Russian strings whose English I corrected?**
Your brief says not to edit translations. But for 38 keys the new English fixes a false
claim, and the Russian still makes it. Examples: "that link has been used" (it may have
timed out), "we can't read scans yet" (we can), "One press and you're on the list" (it's
two). `tests/test_strings.py` fails on these 38 until the Russian is re-checked and
stamped, so **CI is red on this PR until this is answered.** The other 112 changed keys
were re-read: their Russian still says the right thing, and I stamped them. The list is in
`COPY_AUDIT.md` § Russian.
- **Recommend:** yes. I rewrite those 38 Russian lines to match the new meaning, keep their
  existing terms, and stamp them.
- Alternatives: (b) you or a Russian editor do them. (c) I revert those 38 English changes
  and the false claims stay in both languages.

## B. Bugs the audit found (behaviour, not copy — not changed)

Your brief says not to change behaviour to make copy fit. In these, the wrong message comes
from code choosing the wrong branch. **Recommend for all of B:** I fix 2–4 in a separate
follow-up PR (each is a few lines) and file the rest as `targum-internal` issues.
Alternative: file them all as issues.

**2. `/build/<id>` says "We can't make this one" to a build that is on its way.** A pressed
build is in stage `queued`, and the template sends that stage to the error branch. So does
`looking up words` (still being costed). Every press without script, and every reload while
waiting, tells the reader it failed. Fix: add both stages to the "We're making it" branch.
(`press.html.j2`)

**3. The Add page blames the connection when the server refused a file.** A picture over
20 MB, a protected file or a full recording quota all show "We couldn't reach targum. Check
your connection." Fix: show the server's sentence, as the post form already does.
(`add.js`; the patch is written.)

**4. "Nothing marked yet" on Your Progress for Yiddish and Aramaic readers who have marked
hundreds of words.** Those languages have no frequency bands. Fix: a new line — "We have no
word list for this language, so we can't say how common its words are." — or hide the panel.

**5. Link refusals show readers "HTTP 403", curl errors and operator hints** ("install
yt-dlp", "set OPENAI_API_KEY"). Fix: show the reader sentence that already exists for each
status (`job.unreadable.*`), and keep the technical text in the log.

**6. Errors raised mid-build are always English and lose their hint.** (`Library._blame`
callers.) Fix: route them through `refused_in`, as the prepare path does.

**7. A closing account's sign-in says "That link no longer works" or "targum isn't open
yet".** Neither is true. Fix: a server branch that says "This account is being closed. To
keep it, email hello@targum.page."

**8. Re-ticking a translation language may not bring its translations back**, but /you says
"you lose nothing when you untick one". Fix the behaviour (rebuild on re-tick) rather than
the copy. Needs checking in the app first.

**9. Mid-connect sign-in says nothing about why**, and the connection is dropped silently if
the email link opens in another browser. Fix: a line on the sign-in page when a connect is
pending ("Sign in to finish connecting Claude"), and a clear message when it's lost.

**10. The Suggested door on Learn says the known share twice** (reason line and chip). Fix:
skip the chip when the reason already says it.

## C. Credits, cost and "free"

**11. Buttons that spend credits have no cost beside them.** This covers the Add page's card,
the chat's card, and the reader's Translate / Transcribe / Prepare all. The press page, the
set page and Telegram already say "Uses N credits".
- **Recommend:** add "Uses {n} credits" for audio and video, and "Uses none of your credits"
  for text. This reuses the existing `press.page.uses-credits.*` keys. It's a small code
  change.
- Alternative: rely on the standing line on Add ("one credit a minute").

**12. What the spending button is called.** Add says "Open", the chat card "Open this", the
build page "Read this", the set page "Confirm". §6 wants read / listen / watch, or "Open"
when unknown. Your brief wants buttons to name their action.
- **Recommend:** keep §6's verbs. On the build page, say Read / Listen to / Watch this by
  media. Put the cost line (11) right beside the button. Keep "Confirm" on the set page,
  your call in #415. Add one line to the set page: "Unticked texts come out of the
  playlist." (It removes them silently today.)
- Alternative: "Get it ready" everywhere a press spends.

**13. "Free" inside the product.** Four refusals end "The library is always free"
(`job.out-of.*`). From targum playlists say "Free to open" (your wording in #415). §6 says
there is no price inside the product.
- **Recommend:** "The library still opens." and "Opening them uses no credits."
- Alternative: keep both. I'd then record "free" as a §12 exception.

**14. The description search on Add is priced as a clock** ("Looking used 0:07 of your
credits") and called "a turn of conversation, off your credits". §12 2026-09-24 says
chatting is included.
- **Recommend:** "That sounds like what you want to read. Press Continue and we'll look for
  it." Stop showing the clock line, and delete 3 orphan keys.
- Alternative: say it in credits (it rounds to 0).

**15. Is there a paid plan?** §6 and §12 speak of a monthly subscription and a pricing page.
No billing surface exists, and Terms 2.1 says the service is "without charge". The /connect
FAQ says "Chatting is included" without saying included in what.
- **Recommend:** for now, /connect says "Connecting is free, and so are searching the library
  and your word list. Chatting uses no credits. A new text you ask for uses credits, and you
  confirm it first." Revisit when billing exists.
- Alternative: tell me the plan's name and I'll write "included in {plan}".

**16. "Nearly 500 free texts and videos"** on /connect (and the landing twin, not touched).
The catalogue holds 967 entries: 532 in Hebrew, 249 with a published translation.
- **Recommend:** "More than 500 texts and videos", if the count means Hebrew texts. Tell me
  if it means something else.

## D. Legal and consent (meaning, not style)

**17. The privacy notice doesn't match the code.** I didn't touch the legal text. What's off:
- 4.2 lists Hetzner, Resend and Anthropic. The code also sends data to OpenAI, ElevenLabs,
  Google (Gemini, and Google sign-in), Telegram and DataImpulse.
- Resend now sends much more than "authentication messages".
- 3.12 says there's one cookie. The OAuth connect sets a second.
- The waitlist and digest data aren't described.
- **Recommend:** review before `legal_is_public()` is switched on. I can draft the amendments.

**18. The consent line for the `chat` scope** on the approval page reads: "Read what you
write…, keep the lines we correct, get texts and playlists ready…, and add a language you
practise". Its subject is wrong: targum keeps corrections, not the app. "add a language"
is unclear, and adding shelf texts to a playlist is missing.
- **Recommend:** "Send us what you write in a language you're learning, for us to correct.
  Add texts to your playlists, and get new ones ready for you to confirm." Change
  `oauth.SCOPES` to match.
- Alternative: fix only the subject.

**19. Taking back a deletion.** /you says "We wait seven days before deleting." The only way
back is to email hello@targum.page, and that is written only in the legal text.
- **Recommend:** "We wait seven days before deleting. To change your mind, email
  hello@targum.page."

## E. Access, waitlist and the public reading pages

**20. An uninvited address is told "targum isn't open yet."** No next step is given, though
the waitlist exists.
- **Recommend:** add "Join the waitlist and we'll email you when it's your turn." only while
  the front door is open.

**21. Signed-in readers are shown the waitlist pitch** on the parasha, daily and weekly pages.
§6 says someone who has chosen targum is not sold to again.
- **Recommend:** hide the waitlist form and closing section when signed in.

**22. Archived weekly issues say "this week's"** in the hero. I fixed the in-product label
and dateline. The hero is marketing, so I didn't touch it.
- **Recommend:** word the archive hero around the issue's date.

**23. Waitlist and series stop pages carry the Weekly News Digest's tab title and
description.** The series stop page never names the series.
- **Recommend:** pass the title in, and name the series ("Stop emails about {name}?").

## F. Names and new strings

**24. "Your subscriptions" means followed series.** It will read as billing once a paid plan
exists. /you is also called "You", "Your profile" and "the profile page".
- **Recommend:** "Following" for series. "Your profile" for the page (title and link).

**25. "Save as targum"** at the foot of a chat (§12 2026-09-06). A newcomer won't know "a
targum".
- **Recommend:** "Save as a text".
- Alternative: "Save as a targum".

**26. One name for the Claude/ChatGPT feature.** The kicker says "targum Connect", the page
"targum in Claude and ChatGPT", the site foot "Install MCP" (§12 2026-09-28).
- **Recommend:** "targum in Claude and ChatGPT" on /connect and in-product. Keep "Install
  MCP" in the public foot, per §12.

**27. The sign-in page's heading is a tagline** ("Hebrew, with the translation beside it").
§12 2026-08-24 cut this page on purpose.
- **Recommend:** h1 "Sign in to targum", the same as the sign-in email.

**28. Verbs that need new keys** (and new Russian):
- "Start listening" / "Start watching" on the contents page (§6).
- Read / Listen / Watch on the ready email's button.
- "Read the {n} pages" for a scanned PDF, not "Also read the {n} pictures".
- **Recommend:** yes to all three.

**29. Explain levels on Your Progress.**
- **Recommend:** one line under each ladder: "Ulpan classes in Israel run from aleph, for
  beginners, to vav." / "The European scale runs from A1, for beginners, to C2." Plus a
  tooltip on "learned on targum": "Saved as new and since marked known."
- Alternative: keep §12's "the limit is all that is said".

**30. "Unsubscribe" or "Stop these emails"?** The digest foot says one, the series foot the
other.
- **Recommend:** "Unsubscribe" in both.
