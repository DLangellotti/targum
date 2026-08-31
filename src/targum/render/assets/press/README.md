# press marks

Wordmarks of the outlets the weekly cites, for the landing page's "From this week's
reporting in" line and the hero's newspaper-stack imagery. §12 of `design.md` records
why third-party marks appear in their own colours on a page whose palette bans them.

Every file here came from Wikimedia Commons tagged **Public domain** (PD-textlogo:
simple text arrangements below the threshold of originality). Copyright is not the
constraint on these; trademark is. They are used nominatively — to name the outlets an
issue actually cites, never to imply endorsement — and a mark appears only on an issue
page whose sources include that outlet.

| file | outlet | source file on Commons |
|---|---|---|
| `ynet.svg` | ynet | Ynet website logo.svg |
| `walla.svg` | walla | Walla logo.svg |
| `haaretz.svg` | haaretz | Logo Haaretz he 2023 wordmark.svg |
| `globes.svg` | globes | Globes (newspaper) logo.svg |
| `kan11.svg` | kan | Kan11Logo.svg |

Adding one: it must be on Commons (or otherwise verifiably free), and its key in
`PRESS_MARKS` (`render/builder.py`) must match the outlet name exactly as
`weekly/sources.py` records it.

## pages/

The hero's stack: photographs of real front pages, identification-resolution scans
from Wikipedia's articles on each paper.

| file | paper | source file on en.wikipedia |
|---|---|---|
| `pages/yedioth.jpg` | Yedioth Ahronoth | Yedioth Ahronoth cover.jpg |
| `pages/haaretz.jpg` | Haaretz | Haaretz front page.jpg |
| `pages/hayom.jpg` | Israel Hayom | Israel Hayom front page.png |

**These are not free files.** A front page is a copyrighted work; Wikipedia hosts these
thumbnails under its own fair-use rationale, which does not transfer to us. David
decided on 2026-08-31 to ship them anyway — small, decorative, identifying the press
being cited — accepting the risk knowingly (§12). If an outlet objects, take its page
out of the stack; the layout degrades gracefully to fewer papers. Note the Yedioth
scan is a historic front page, not a current one.
