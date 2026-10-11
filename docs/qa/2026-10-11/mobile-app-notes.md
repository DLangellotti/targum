# Notes for the mobile app — from the QA pass of 2026-10-11

Limited to what this audit found. Everything below was observed in browser emulation, not on
a device.

## Behaviour the app should own natively

- **Back.** Onboarding needed a history entry per step before Android's back gesture behaved
  (QA-004). Every multi-step surface (onboarding, a reader's sheets, the drawer, Library
  See all with its hash routes) relies on browser history for back. An app needs one
  explicit back stack: sheet → step → page.
- **Sessions that end.** A lost session lands a returning reader on "COMING SOON" (D2). An app
  should hold the account and refresh it silently, and never show the public holding page
  to someone who has signed in before.
- **Sign-in by mailed link.** The link opens in whatever browser the mail app chooses, which
  may not be the app. Universal Links / App Links need the `/account/enter` path, and the
  page's "press to sign in" step should be kept: it exists so that link scanners don't
  burn the token.
- **Offline.** The service worker keeps saved texts and falls back to "Saved on this device"
  only if that page was itself kept (READER-03). An app should keep its own offline store and
  index, and always have an offline screen of its own. iOS's 7-day storage eviction for web
  apps (accepted for the browser, 2026-10-08) does not apply to an app's own storage.
- **The keyboard.** Focusing the assistant's box on a phone would raise the keyboard over a
  sheet the reader may only want to read, so the browser fix deliberately does not focus it
  on a touch screen (QA-009). In an app, raise the keyboard only on an explicit tap.
- **Recording.** `/add`'s Record names the clip `voice-note.webm` and classifies by extension,
  so a voice note is called a video (ACCOUNT-08). Safari records `audio/mp4`. An app should
  pass the MIME type it recorded, not a filename.

## Shared pieces the app can reuse as they now stand

- **Touch reach.** The rule (§8, 44px under a coarse pointer) is enforced by
  `test_brand.py`'s registry. Two traps this audit found are now fixed: an `::after` reach
  clipped by `overflow: hidden` on its own element (QA-013), and a reach centred with
  `inset: 0; margin: auto`, which CSS centres vertically but not horizontally (QA-005). Use
  `inset-inline: min(0px, calc(50% - 22px))`.
- **Interface strings.** A page now carries every catalogued key its own scripts call
  (QA-007). An app consuming `strings/*.json` should load the whole catalogue for its
  language; the page-by-page prefix lists were the source of the Russian gaps.
- **Refusals.** Server refusals go through `serve.told`. On a hosted box it now gives
  operator-only errors (`OffHere`) the reader's sentence, with no machine detail (QA-010).
  An app can show `job.error` and `job.blocked` as they come.
- **Build states.** `done`, `failed` and `blocked` are all settled (`SETTLED` in `serve.py`).
  Only other stages are "getting ready" (QA-019).

## Layout facts worth carrying over

- Breakpoints in use: phone under 40rem (bottom bar of places, sheets from the foot); the
  desk header wraps to two rows under 56rem (QA-001); the reader has its own 46/60/64rem
  steps.
- Russian labels run 15–40% longer than English. Every overflow found at 320px was Russian
  or a language name with its badge ("Арамейский · Экспериментальный"). Design phone layouts
  in Russian first.
- `viewport-fit=cover` is set on desk pages but not on readers or public pages. Readers use
  `env(safe-area-inset-bottom)` without it, so on a notched iPhone those insets read 0.
  Check this on a device before relying on it.
