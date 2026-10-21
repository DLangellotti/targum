"""One search, everywhere (design.md §12, "One search, everywhere", 2026-10-09).

What a typed line is compared with, and how. A title in the catalogue is Hebrew script,
spelled the way its edition spelled it; a reader types the way they learned it — with or
without the vowel letters, in Latin letters, or in English. So both sides are folded to
one spelling before they meet, and a short table names the texts people ask for by a
transliterated name ("tehillim") or a name in another language ("Chekhov").

Local and free: nothing here asks a model, and the table is a file a person edits.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

#: Hebrew points and cantillation, the Russian stress mark and anything else that sits
#: on a letter rather than being one. Removed, so a pointed title meets an unpointed line.
_MARKS = re.compile(r"[֑-ׇֽֿׁׂׅׄ̀-ͯ]")
#: What only punctuates a name: geresh and gershayim, quotation marks of every kind and
#: the apostrophe (צ׳כוב, צ'כוב, תנ״ך, תנ"ך).
_QUOTES = re.compile(r"[׳״'\"`’‘“”״׳]")
#: Joiners that are spaces to a reader: the maqaf, hyphens and dashes.
_JOINERS = re.compile(r"[־\-–—_/·.,:;!?()\[\]{}«»]")
_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ", "ё": "е"})
_SPACES = re.compile(r"\s+")
#: Vav and yod inside a word: the vowel letters full spelling adds and defective
#: spelling leaves out (ירושלים / ירושלם, שולחן / שלחן). Kept at the head of a word,
#: where they are consonants.
_VOWEL_LETTERS = re.compile(r"(?<=[א-ת])[וי]+")
_HEBREW = re.compile(r"[א-ת]")
_LATIN = re.compile(r"[a-z]")


def fold(text: str) -> str:
    """One spelling for comparing: no points, no stress marks, no quotation marks, final
    letters as their ordinary form, ё as е, Latin accents off, lower case, one space."""
    if not text:
        return ""
    bare = _MARKS.sub("", unicodedata.normalize("NFD", text))
    bare = _QUOTES.sub("", bare)
    bare = _JOINERS.sub(" ", bare)
    bare = unicodedata.normalize("NFC", bare).lower().translate(_FINALS)
    return _SPACES.sub(" ", bare).strip()


def title_key(title: str) -> str:
    """A title as two copies of one text agree on it: folded, and without the emoji or
    punctuation one copy's source added (a video's "… בירושלים? 🌱")."""
    return _SPACES.sub(" ", re.sub(r"[^\w\s]", "", fold(title))).strip()


def skeleton(folded: str) -> str:
    """A folded line without the vowel letters inside its Hebrew words, so full and
    defective spelling meet: ירושלים and ירושלם are both ירשלמ."""
    return _VOWEL_LETTERS.sub("", folded)


def script(text: str) -> str:
    """ "he" for a line in Hebrew letters, "la" for Latin, "" for anything else
    (Cyrillic among it, which needs no table)."""
    if _HEBREW.search(text):
        return "he"
    if _LATIN.search(fold(text)):
        return "la"
    return ""


def _latin_key(text: str) -> str:
    """A transliteration reduced to what spellers agree on: letters only, kh and ch as
    h, tz as ts, ei as e, and no doubled letters (tehillim, tehilim, t'hillim)."""
    bare = re.sub(r"[^a-z]", "", fold(text))
    for was, now in (("tch", "ch"), ("kh", "h"), ("ch", "h"), ("tz", "ts"), ("ei", "e")):
        bare = bare.replace(was, now)
    return re.sub(r"(.)\1+", r"\1", bare)


#: The names people ask for in Latin letters, or in another language, and what the shelf
#: calls the same thing. A key is matched after `_latin_key`; the values are searched as
#: if typed. Kept short on purpose: the catalogue's English titles already answer
#: "Psalms", and this is for the names it does not carry.
ALIASES: dict[str, tuple[str, ...]] = {
    # The Tanakh, by the names the books are read by.
    "tanakh": ("תנך", "Tanakh"),
    "tanach": ("תנך", "Tanakh"),
    "torah": ("תורה", "Torah"),
    "bereshit": ("בראשית", "Genesis"),
    "beresheet": ("בראשית", "Genesis"),
    "breshit": ("בראשית", "Genesis"),
    "shemot": ("שמות", "Exodus"),
    "vayikra": ("ויקרא", "Leviticus"),
    "bamidbar": ("במדבר", "Numbers"),
    "devarim": ("דברים", "Deuteronomy"),
    "yehoshua": ("יהושע", "Joshua"),
    "shoftim": ("שופטים", "Judges"),
    "shmuel": ("שמואל", "Samuel"),
    "melahim": ("מלכים", "Kings"),
    "yeshayahu": ("ישעיהו", "Isaiah"),
    "yirmiyahu": ("ירמיהו", "Jeremiah"),
    "yehezkel": ("יחזקאל", "Ezekiel"),
    "terasar": ("תרי עשר",),
    "tehilim": ("תהילים", "תהלים", "Psalms", "Tehillim"),
    "tilim": ("תהילים", "Psalms"),
    "thilim": ("תהילים", "Psalms"),
    "mishle": ("משלי", "Proverbs"),
    "iyov": ("איוב", "Job"),
    "shirhashirim": ("שיר השירים", "Song of Songs"),
    "rut": ("רות", "Ruth"),
    "eha": ("איכה", "Lamentations"),
    "kohelet": ("קהלת", "Ecclesiastes"),
    "ester": ("אסתר", "Esther"),
    "esther": ("אסתר", "Esther"),
    "nehemia": ("נחמיה", "Nehemiah"),
    "divrehayamim": ("דברי הימים", "Chronicles"),
    # The rabbinic shelf.
    "mishna": ("משנה", "Mishnah"),
    "mishnayomit": ("משנה יומית", "Mishnah Yomit"),
    "gemara": ("גמרא", "Talmud"),
    "talmud": ("תלמוד", "Talmud"),
    "rambam": ("משנה תורה", 'רמב"ם', "Mishneh Torah"),
    "mishnetorah": ("משנה תורה", "Mishneh Torah"),
    "pirkeavot": ("פרקי אבות", "Avot"),
    "avot": ("אבות", "Avot"),
    "sidur": ("סידור", "Siddur"),
    "hagada": ("הגדה", "Haggadah"),
    "parasha": ("פרשת השבוע", "Weekly portion"),
    "parashat": ("פרשת", "Weekly portion"),
    "dafyomi": ("דף יומי", "Daf Yomi"),
    "onkelos": ("אונקלוס", "Onkelos"),
    "rashi": ('רש"י', "Rashi"),
    # Places and names asked for in English letters.
    "yerushalayim": ("ירושלים", "Jerusalem"),
    "jerusalem": ("ירושלים", "Иерусалим"),
    "telaviv": ("תל אביב", "Tel Aviv"),
    "israel": ("ישראל", "Израиль"),
    "shalom": ("שלום",),
    # Authors, by the name another shelf knows them by.
    "chekov": ("צ'כוב", "Чехов"),
    "hekov": ("צ'כוב", "Чехов"),
    "chehov": ("צ'כוב", "Чехов"),
    "hehov": ("צ'כוב", "Чехов"),
    "tolstoy": ("טולסטוי", "Толстой"),
    "tolstoi": ("טולסטוי", "Толстой"),
    "pushkin": ("פושקין", "Пушкин"),
    "dostoevsky": ("דוסטויבסקי", "Достоевский"),
    "gogol": ("גוגול", "Гоголь"),
    "turgenev": ("טורגנייב", "Тургенев"),
    "agnon": ("עגנון",),
    "bialik": ("ביאליק", "Бялик"),
    "brener": ("ברנר", "Brenner"),
    "herzl": ("הרצל", "Herzl"),
    "mendele": ("מנדלי", "Mendele"),
    "shalomaleihem": ("שלום עליכם", "Sholem Aleichem"),
    "sholemaleihem": ("שלום עליכם", "Sholem Aleichem"),
    "benyehuda": ("בן יהודה", "Ben-Yehuda"),
    "mapu": ("מאפו", "Mapu"),
    "ahadhaam": ("אחד העם", "Ahad Ha'am"),
    "rahel": ("רחל", "Rachel"),
    # And the other way round: a name typed in Cyrillic finds the Hebrew shelf's copy.
    "чехов": ("צ'כוב", "Chekhov"),
    "толстой": ("טולסטוי", "Tolstoy"),
    "пушкин": ("פושקין", "Pushkin"),
    "иерусалим": ("ירושלים", "Jerusalem"),
}


def _alias_key(text: str) -> str:
    folded = fold(text)
    if _LATIN.search(folded):
        return _latin_key(folded)
    return folded.replace(" ", "")


def variants(query: str) -> list[str]:
    """What one typed line is searched as: itself, and what the table says it is also
    called. Each comes back folded."""
    said = fold(query)
    if not said:
        return []
    out = [said]
    for name in ALIASES.get(_alias_key(query), ()):
        folded = fold(name)
        if folded and folded not in out:
            out.append(folded)
    return out


@dataclass(frozen=True)
class Matcher:
    """A query, folded and expanded once, that scores the things it is asked about."""

    wanted: tuple[str, ...]

    @classmethod
    def of(cls, query: str) -> Matcher:
        return cls(tuple(variants(query)))

    def __bool__(self) -> bool:
        return bool(self.wanted)

    def score(self, title: str, *others: str) -> int:
        """How well a thing named `title`, with `others` said about it (its English, its
        author, its blurb), answers the query: 0 for not at all. A title that is the
        query beats one that starts with it, beats one that holds it, beats a match
        anywhere else; a match on a folded spelling counts a step under the same match
        spelled as typed, and a match on another name for it (the table) a step under
        that."""
        best = 0
        head = fold(title)
        rest = fold(" ".join(other for other in others if other))
        for at, want in enumerate(self.wanted):
            lower = 1 if at else 0
            for hay, top in ((head, 9), (rest, 3)):
                found = _found(want, hay, top)
                if found:
                    best = max(best, found - lower)
        return best


def _found(want: str, hay: str, top: int) -> int:
    if not hay:
        return 0
    if top > 3:
        if hay == want:
            return top
        if hay.startswith(want):
            return top - 1
    words = want.split()
    if all(word in hay for word in words):
        return top - 2 if top > 3 else top
    bones = skeleton(hay)
    if all(skeleton(word) in bones for word in words if skeleton(word)):
        return top - 3 if top > 3 else top - 1
    return 0


#: The three bands the Library shelves by (design.md §12, "The Library is shelved by how
#: much you'd follow", 2026-10-09): the share of a text's words this reader knows.
BANDS = (("now", 0.9), ("stretch", 0.75), ("hard", 0.0))


def band(known: float | None) -> str:
    """Read it now, A stretch or Hard for now, by the share known; "" where unmeasured."""
    if known is None:
        return ""
    for name, floor in BANDS:
        if known >= floor:
            return name
    return "hard"


def matching_words(query: str, words: Iterable[tuple[str, str, int | None]]) -> list[str]:
    """Which of a reader's own words a query names: `words` is (lemma, meaning, status).

    A line in the language's own letters meets a dictionary form, in either spelling; a
    line in Latin letters meets only what the reader wrote as its meaning, or a name the
    table gives in the language's letters — never the dictionary, because a word the
    reader has never met is not one they are looking for (David, 2026-10-08)."""
    asked = variants(query)
    if not asked:
        return []
    latin = script(query) == "la"
    found: list[str] = []
    for lemma, meaning, _ in words:
        bare = fold(lemma)
        if not bare:
            continue
        said = fold(meaning)
        hit = False
        for want in asked:
            if script(want) == "la":
                bounded = rf"(?<![a-z]){re.escape(want)}(?![a-z])"
                hit = hit or bool(latin and said and re.search(bounded, said))
            elif want == bare or skeleton(want) == skeleton(bare):
                hit = True
        if hit and lemma not in found:
            found.append(lemma)
    return found
