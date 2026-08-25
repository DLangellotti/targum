"""Is this a Hebrew word, and how ordinary a one?

Two registers, because targum is read in both. A reader of Ha'aretz and a reader of
Samuel are not reading the same language, and a lexicon that knows only one of them is
wrong about the other in a way that looks like knowledge: wordfreq has never heard of
וְעִקֵּשׁ, and the Tanakh has never heard of מקרר.

So there are two corpora and the morphology between them:

- **Modern**, from wordfreq's blended Hebrew — Wikipedia, subtitles, news, the web. It
  is a list of *forms*, so inflections are in it: not only ספר but ספרים and לספרים.
- **Biblical**, from the Tanakh lemma table already shipped for difficulty bands
  (`annotate/tanakh.json`, twelve thousand lemmas counted off the corpus itself). It is
  a list of *lemmas*, so getting a word to it means taking the word apart first.
- **The morphology**, which is what makes a lemma list usable on running text. Hebrew
  writes its conjunctions, articles and prepositions onto the front of a word and its
  possessives onto the back, so וכשלמלכיהם is one string and six morphemes, and none of
  the three lists above will ever contain it.

Two questions get asked here, and they want opposite things.

`known()` asks *could this be a word at all* — asked of a word before it is taken apart.
It should say yes too often rather than too rarely: the cost of a wrong yes is a seam
left in the text, and the cost of a wrong no is a word the reader wrote being split in
half. So it peels generously and accepts anything underneath.

`strength()` asks *how sure are we this is a real word* — asked of the halves. It reads
the form itself against modern usage and only reduces to a lemma for the biblical side.
"""

from __future__ import annotations

from functools import cache, lru_cache

# The letters Hebrew writes onto the front of a word: the conjunction, the article, the
# prepositions, the relativiser. They stack — וכשה is four of them — which is why a
# lemma list alone cannot read a Hebrew sentence.
CLITICS = frozenset("והבכלמש")

# What it writes onto the back: possessives, objects, plurals, the construct ending.
# Longest first, so מלכיהם gives up יהם before it gives up ם.
SUFFIXES = (
    "יהם",
    "יהן",
    "יכם",
    "יכן",
    "ינו",
    "ותיו",
    "הם",
    "הן",
    "כם",
    "כן",
    "נו",
    "יו",
    "יה",
    "ים",
    "ות",
    "תי",
    "תם",
    "תן",
    "ני",
    "ם",
    "ן",
    "ך",
    "ו",
    "י",
    "ה",
)

# A letter that ends a word is written in its final form, so a stem uncovered by taking
# an ending off has to be given its ending back before it will match anything: מלכם is
# מלכ plus ם, and the word underneath is מלך.
_FINAL = str.maketrans("כמנפצ", "ךםןףץ")

# What a Tanakh band is worth on the modern scale, so one bar can be set across both
# registers. Band 1 is the handful of lemmas carrying half of all scripture; band 6 is
# where the hapax legomena live, and a word that appears once in the Tanakh is not
# evidence of anything.
_BIBLICAL_STRENGTH = {1: 5.5, 2: 5.0, 3: 4.5, 4: 4.2, 5: 3.6, 6: 2.0}

# Below this a stem is too short to mean anything: every two-letter run of Hebrew is
# some word's stem, and accepting them makes the lexicon say yes to everything.
_MIN_STEM = 2


@cache
def _biblical() -> dict[str, int]:
    from .annotate.biblical import _table

    return _table()[0]


@lru_cache(maxsize=16384)
def _zipf(word: str) -> float:
    """Modern frequency, or 0 for a word the corpus has never seen.

    wordfreq is an optional extra. Without it the modern half of the lexicon is empty,
    which callers have to be able to live with — see `available()`.
    """
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return 0.0
    return zipf_frequency(word, "he")


def available() -> bool:
    """Whether there is anything behind the modern half of this."""
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        return bool(_biblical())
    return True


@lru_cache(maxsize=16384)
def peel(form: str) -> frozenset[str]:
    """Every word this form could be once its clitics and endings are taken off.

    Generous on purpose, and never exhaustive: it produces candidates for a lexicon to
    recognise, not an analysis. וכשלמלכיהם yields מלכיהם, מלכי and מלך among others, and
    it is the lists that decide which of those is a word.
    """
    stems = {form}
    # Up to four, which is as many as Hebrew stacks: וכשלמלכיהם is ו־כ־ש־ל and then a
    # word.
    for n in (1, 2, 3, 4):
        if len(form) - n >= _MIN_STEM and all(c in CLITICS for c in form[:n]):
            stems.add(form[n:])

    out = set(stems)
    for stem in stems:
        for suffix in SUFFIXES:
            if not stem.endswith(suffix) or len(stem) - len(suffix) < _MIN_STEM:
                continue
            bare = stem[: -len(suffix)]
            out.add(bare)
            # The final form the ending was covering up, and the ה a feminine noun drops
            # in the construct: מלכותנו is מלכות, and סגולתנו is סגולה.
            out.add(bare[:-1] + bare[-1].translate(_FINAL))
            if bare.endswith("ת"):
                out.add(bare[:-1] + "ה")
    return frozenset(out)


def known(form: str) -> bool:
    """Whether this could be a Hebrew word — modern, biblical, or inflected from either.

    The generous question. A yes here only ever stops something from happening.
    """
    if not form:
        return False
    table = _biblical()
    return any(_zipf(candidate) > 0 or candidate in table for candidate in peel(form))


def strength(form: str) -> float:
    """How ordinary a word this is, on wordfreq's zipf scale, in whichever register.

    The strict question. Modern is read off the form as written, because wordfreq holds
    forms; biblical goes through `peel`, because the Tanakh table holds lemmas. A word
    ordinary in either register is ordinary — a reader of Psalms meets וְחַסְדּוֹ as
    often as a reader of the news meets ממשלה.
    """
    if not form:
        return 0.0
    best = _zipf(form)
    table = _biblical()
    for candidate in peel(form):
        band = table.get(candidate)
        if band is not None:
            best = max(best, _BIBLICAL_STRENGTH.get(band, 0.0))
    return best
