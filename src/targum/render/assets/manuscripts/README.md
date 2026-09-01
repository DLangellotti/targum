# the manuscripts

One picture for each daily learning cycle's hero. §12 of `design.md` records why a page
about a Jewish text may carry a picture of one at all, and the conditions.

Each cycle gets a manuscript of the text it reads, rather than a portrait of the person
behind it. That was a decision and not a shortage — though it is also a shortage. There
is no likeness of Judah the Prince: Wikimedia Commons has his burial cave at Beit
She'arim, a map, and nothing else, and the cave photograph is **CC BY-SA**, which this
shelf refuses for the reason `ingest/fetch/sefaria.py` gives at length — a build makes
derivatives and ShareAlike would carry onto them. Every later "portrait" of a sage of the
Mishnah is a nineteenth-century invention, and printing one as the hero of a page about
his book is a fabricated face presented as a fact. A page of the book is neither.

| file | what | source | licence |
|---|---|---|---|
| `mishnah.jpg` | MS Kaufmann A50, the oldest complete Mishnah, Seder Zeraim | [Mishnah-Kaufmann-A-Zeraim](https://commons.wikimedia.org/wiki/File:Mishnah-Kaufmann-A-Zeraim-HB44722.pdf), Hungarian Academy of Sciences, Wikimedia Commons | **Public domain** |
| `aleppo.jpg` | The Aleppo Codex, written by Shlomo ben Buya'a, c. 930 | [Aleppo Codex (Deut)](https://commons.wikimedia.org/wiki/File:Aleppo_Codex_(Deut).jpg), Wikimedia Commons | **Public domain** |
| `leningrad.jpg` | The Leningrad Codex, written by Shmuel ben Ya'akov, 1008 | [Leningrad Codex Carpet page e](https://commons.wikimedia.org/wiki/File:Leningrad_Codex_Carpet_page_e.jpg), Wikimedia Commons | **Public domain** |
| `psalms.jpg` | David with his lyre, from the synagogue floor at Gaza, 508 | [King David as Orpheus in a synagogue mosaic](https://commons.wikimedia.org/wiki/File:King_David_as_Orpheus_in_a_synagogue_mosaic_-_Google_Art_Project.jpg), Google Art Project, Wikimedia Commons | **Public domain** |

Public domain asks for nothing and the page credits each of them anyway — the same rule
the recordings and the scroll follow, and for the same reason: a credit that lives only
in a repository is a credit nobody reading the page ever sees.

The Kaufmann page is worth knowing about for a second reason. It is the manuscript
`ingest/fetch/sefaria.py` weighs and turns down: the better text, pointed, public domain,
and impossible to pair with an English numbered to the printed division. The page shows
the reader the manuscript the shelf could not use.

**The Psalms one is a picture of David, and that is not a departure from the paragraph
above.** What the Mishnah page refuses is an invented face: there is no likeness of Judah
the Prince, so any portrait is a nineteenth-century artist's guess printed as a fact. The
Gaza mosaic is not a guess about what David looked like — it is a floor a Jewish community
laid in 508 and labelled דויד in tesserae, and it is as much an artefact of how the Psalms
were read as a codex is. A picture may be of a thing and must not be a claim about one;
this is a picture of a thing.

It is the third picture tried, and the two before it are worth recording. The first, `File:Psalms Scroll.jpg`, is the
famous shot of the whole scroll — and it is not a photograph of a scroll, it is a scan of
a book plate: the scroll runs along the top third and the rest is a printed transcription
in tiny type with a caption under it. At the size the hero draws it that reads as a page
of a book, which is the one thing this panel must not look like. Cropping to the scroll
band alone leaves a strip about five times as wide as it is tall, and filling a 2:1 panel
from it means upscaling a 380 px crop two and a half times. `File:Psalm 118 11Q5.jpg` replaced it and is a good picture — a photograph of one column,
big enough to crop without enlarging anything, with the Tetragrammaton in paleo-Hebrew.
It is the one to go back to if the mosaic is ever the wrong note.

Each is cropped to 2:1 and saved at 1000 px, which is the widest the panel is ever drawn,
and inlined as a `data:` URI so the page still fetches nothing. Swapping any of them is
one file and no code — the crop is taken from the middle of the page, where a manuscript
keeps its writing, and `scripts/` has no tool for it because it was four images once.
