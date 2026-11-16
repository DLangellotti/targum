"""A practice for each hard spot, built from lines the reader already read (targum-internal#440).

design.md §12, "A practice for every hard spot" (2026-10-13), and the research it rests
on (targum-internal, research/hard-spots-2026-10-11, "A practice item is a meaning
decision on a sentence the reader finished"): a grammar point is practised as a choice
between two answers about one word, in a line the reader has read to its end, never as a
paradigm drill. One worked example opens a round, five items follow, and each answer is
followed by the correct option, the rule that decided it, and one real line where the
other answer is right.

**The register is the fact the stage standard reads** (`REGISTERED`, read by
`stages._practices`). A spot is registered here when its practice exists, and the test
that keeps the badge honest sees it from that day.

**Nothing here spends, and nothing here is a source of truth.** Items are read off the
annotation a build already wrote, in texts the reader finished, and cached beside it as
`practice.json`, stamped with the files it came from, exactly as `meetings.json` is.

**The encounter count is the ledger** (targum-internal#439). How many lines a reader has
met a spot in is counted from the sections they finished, which is also what "met" means
everywhere else on targum (design.md §12, ""Met" means a section you finished"). It is
derived, never stored: exported with the reader's finished sections and gone with them.
A spot is offered once it has been met `ENCOUNTERS` times across `TEXTS` texts.

**Holding the reader between 60 and 85 per cent.** Each item is easy or hard: a hard
item's wrong answer is the one learners confuse with the right one (pa'al against pi'el,
he against I), an easy one's is further off. Over the last `WINDOW` answers on a spot,
above the band the round draws hard items, below it easy ones, and inside it both.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import write_atomic

#: The cached file's name, beside `annotation.json`.
CACHE = "practice.json"

#: The file's shape. Bumped when the encoding changes; an older file is rebuilt for free.
#: 2 (2026-10-21) adds the vav-consecutive's candidates (targum-internal#449), and 3 the
#: pronoun suffixes' (targum-internal#450); 4 drops governed prepositions from Biblical
#: texts, where the spot is declared out (targum-internal#454).
#:
#: A new spot needs no bump: the file also records the spots it was counted for
#: (`spots_key`), and a file counted before a spot was registered is rebuilt on its next
#: read (qa on targum#1295). Bump this only when the encoding of a row changes.
VERSION = 4


def spots_key() -> str:
    """Every registered spot's short key, sorted and joined: what a cached file was
    counted for. Registering a spot changes it, so every text gets the new spot without a
    bump that each practice's PR would fight over."""
    return ",".join(sorted({KEYS[name] for spots in REGISTERED.values() for name in spots}))


#: When a spot is offered: met in this many lines, across this many texts (the research's
#: "about six attended encounters across at least two texts").
ENCOUNTERS = 6
TEXTS = 2

#: A round: one worked example, then this many items.
ROUND = 5

#: The answers the band is held over, and the band.
WINDOW = 20
LOW, HIGH = 0.60, 0.85

#: Days to the next round of a spot, by its step on the ramp: one to two days, then three
#: to four, then widening (the research's schedule).
INTERVALS = (1, 3, 7, 14, 30)


@dataclass(frozen=True)
class Practice:
    """One hard spot's practice: what it asks, and how it is done.

    `kind` is "choice" (two answers about one word in a read line) or "lens" (the spot's
    surface is a lens, by decision: design.md §12 records which and why)."""

    spot: str
    kind: str
    ask: str


#: The practices that exist, per language, by the hard spot's name in `stages.HARD_SPOTS`.
REGISTERED: dict[str, dict[str, Practice]] = {
    "he": {
        "root and binyan": Practice("root and binyan", "choice", "practice.ask.binyan"),
        "nikkud and homographs": Practice(
            "nikkud and homographs", "choice", "practice.ask.homograph"
        ),
        "tense, person and the participle": Practice(
            "tense, person and the participle", "choice", "practice.ask.tense"
        ),
        "gender and number agreement": Practice(
            "gender and number agreement", "choice", "practice.ask.agreement"
        ),
        "construct state and definiteness": Practice(
            "construct state and definiteness", "choice", "practice.ask.construct"
        ),
        "stress and pronunciation": Practice(
            "stress and pronunciation", "choice", "practice.ask.stress"
        ),
        # A lens, not a question: the research found this spot immune to feedback
        # (design.md §12, "Lenses wait for a second read", 2026-10-13).
        "governed prepositions and et": Practice("governed prepositions and et", "lens", ""),
        # Past or future, for a vav and a future form in a Biblical line: the narrative
        # vav against the plain "and" (targum-internal#449, 2026-10-21).
        "the vav-consecutive": Practice("the vav-consecutive", "choice", "practice.ask.vav"),
        # Whose, or to whom, for a word with a pronoun on the end, in both registers: the
        # suffix the line has against the one it is taken for (targum-internal#450).
        "pronoun suffixes": Practice("pronoun suffixes", "choice", "practice.ask.suffix"),
    },
    # French's first (targum-internal#644's Beta list, 2026-11-16): masculine or feminine
    # for a noun in a French line, as the card says it, with the ending the card names
    # (`annotate/endings.py`) deciding which items are the easy kind.
    "fr": {
        "gender": Practice("gender", "choice", "practice.ask.gender"),
        # Register, not error (D5, 2026-11-05): formal or informal for a negation, and who
        # an *on* is, both as `annotate/french_register.py` reads them for the card.
        "register: ne-drop and on/nous": Practice(
            "register: ne-drop and on/nous", "choice", "practice.ask.register"
        ),
    },
}

#: Short keys for the spots, as the cache, the store and the page name them.
KEYS: dict[str, str] = {
    "root and binyan": "binyan",
    "nikkud and homographs": "homograph",
    "tense, person and the participle": "tense",
    "governed prepositions and et": "governed",
    "gender and number agreement": "agreement",
    "construct state and definiteness": "construct",
    "stress and pronunciation": "stress",
    "the vav-consecutive": "vav",
    "pronoun suffixes": "suffix",
    "gender": "gender",
    "register: ne-drop and on/nous": "register",
}
SPOTS: dict[str, str] = {key: name for name, key in KEYS.items()}


# -- candidates, read off one text -------------------------------------------------------

#: The binyan a learner confuses with each one, and one that is further off.
CONFUSED = {
    "פעל": "פיעל",
    "פיעל": "פעל",
    "הפעיל": "פיעל",
    "נפעל": "פעל",
    "התפעל": "פיעל",
    "פועל": "פיעל",
    "הופעל": "הפעיל",
}
DISTANT = {
    "פעל": "התפעל",
    "פיעל": "נפעל",
    "הפעיל": "התפעל",
    "נפעל": "הפעיל",
    "התפעל": "פעל",
    "פועל": "הפעיל",
    "הופעל": "פעל",
}

#: Person a learner confuses with each one.
PERSONS = {"1": "3", "2": "3", "3": "1"}
TENSES = {"Past": "Fut", "Fut": "Past"}


@dataclass(frozen=True)
class Candidate:
    """One word in one line that a spot can ask about: its place, the right answer and the
    wrong one as codes, and whether the wrong one is the confusable kind."""

    spot: str
    segment: str
    start: int
    end: int
    answer: str
    contrast: str
    hard: bool


def _feats(feats: object) -> dict[str, str]:
    return dict(part.partition("=")[::2] for part in str(feats or "").split("|") if "=" in part)


def _code(feats: Mapping[str, str], keys: Sequence[str]) -> str:
    return "|".join(f"{key}={feats[key]}" for key in keys if feats.get(key))


def candidates(token: Mapping[str, Any], segment: str) -> Iterator[Candidate]:
    """What each spot can ask about one stored token. Hebrew only: the features are DICTA's
    and the binyanim its names."""
    from .annotate.pronounce import STRESS_GUESSED, STRESS_MARK, guessed, syllables

    pos = str(token.get("pos") or "")
    feats = _feats(token.get("feats"))
    start, end = int(token.get("start") or 0), int(token.get("end") or 0)

    def made(spot: str, answer: str, contrast: str, hard: bool) -> Candidate:
        return Candidate(spot, segment, start, end, answer, contrast, hard)

    if pos == "VERB":
        binyan = str(token.get("binyan") or "")
        if binyan in CONFUSED:
            yield made("binyan", binyan, CONFUSED[binyan], True)
            yield made("binyan", binyan, DISTANT[binyan], False)
        tense, person = feats.get("Tense", ""), feats.get("Person", "")
        if tense in TENSES and person in PERSONS:
            said = {**feats}
            keys = ("Tense", "Person", "Gender", "Number")
            other = {**said, "Person": PERSONS[person]}
            if PERSONS[person] != "3":
                other.pop("Gender", None)
            yield made("tense", _code(said, keys), _code(other, keys), True)
            yield made(
                "tense", _code(said, keys), _code({**said, "Tense": TENSES[tense]}, keys), False
            )
    if (
        pos in ("ADJ", "VERB")
        and feats.get("Gender") in ("Masc", "Fem")
        and feats.get("Number")
        in (
            "Sing",
            "Plur",
        )
    ):
        if pos == "ADJ" or feats.get("VerbForm") == "Part" or feats.get("Tense") == "Pres":
            gender, number = feats["Gender"], feats["Number"]
            agrees = f"Gender={gender}|Number={number}"
            flipped = "Fem" if gender == "Masc" else "Masc"
            count = "Plur" if number == "Sing" else "Sing"
            yield made("agreement", agrees, f"Gender={flipped}|Number={number}", True)
            yield made("agreement", agrees, f"Gender={gender}|Number={count}", False)
    if pos == "NOUN":
        bound = feats.get("Definite") == "Cons"
        # A masculine singular in the construct is spelled as it stands alone: only the
        # next word says so, which is the hard kind.
        plain = feats.get("Gender") == "Masc" and feats.get("Number") == "Sing"
        if bound:
            yield made("construct", "Cons", "Free", plain)
        elif feats.get("Definite") == "Def":
            yield made("construct", "Free", "Cons", plain)
    ipa = str(token.get("ipa") or "")
    surface = str(token.get("surface") or "")
    if ipa and " " not in ipa and syllables(ipa) > 1 and STRESS_MARK in ipa:
        if not guessed(surface, ipa) & STRESS_GUESSED:
            moved = _moved_stress(ipa)
            if moved:
                yield made("stress", ipa, moved, True)


def vav_candidates(token: Mapping[str, Any], pointed: str, segment: str) -> Iterator[Candidate]:
    """Past or future for a verb in a Biblical line that opens with a vav (targum-internal
    #449). `pointed` is the word as the line writes it, with its points: the stored surface
    of a verse is bare, and the points are the whole difference.

    The narrative vav (וַיֹּאמֶר, `annotate.vav_consecutive`) is past, though the form is
    the future's; that item is the easy kind. A plain vav, with a shva or a shureq, on a
    verb tagged future (וְיֹאמַר, Open Scriptures' `Vqi`) stays future, and is the hard
    kind: it is the one a reader who has learned "the vav makes it past" gets wrong. Each
    is the other's contrast line."""
    from .annotate.vav_consecutive import DAGESH, SHVA, VAV, consecutive, pointed_letters

    if str(token.get("pos") or "") != "VERB":
        return
    start, end = int(token.get("start") or 0), int(token.get("end") or 0)
    if consecutive(pointed):
        yield Candidate("vav", segment, start, end, "Past", "Fut", False)
        return
    letters = pointed_letters(pointed)
    if len(letters) < 3 or letters[0][0] != VAV or _feats(token.get("feats")).get("Tense") != "Fut":
        return
    marks = letters[0][1]
    # A shureq is the vav's own dagesh with no vowel beside it: וּתְדַבֵּר.
    if SHVA in marks or marks == frozenset({DAGESH}):
        yield Candidate("vav", segment, start, end, "Fut", "Past", True)


def suffix_candidates(token: Mapping[str, Any], pointed: str, segment: str) -> Iterator[Candidate]:
    """Whose, or to whom, for a word with a pronoun on the end (targum-internal#450).
    `pointed` is the word as the line writes it, whose points say ־ךָ from ־ךְ.

    The answer is the card's own words, so the practice says it as the card does, with its
    code before a colon for the rule: "3mp:before them". Two contrasts each, from
    `suffixes.CONFUSED`: the look-alike (ו against י, ם against ן) is the hard kind, and a
    different person the easy one."""
    from .annotate.suffixes import CONFUSED, reading
    from .annotate.suffixes import said as named

    pos = str(token.get("pos") or "") or None
    lemma = str(token.get("lemma") or "")
    built = str(token.get("built") or "") or None
    code = reading(
        surface=str(token.get("surface") or ""), built=built, pos=pos, lemma=lemma, pointed=pointed
    )
    if code not in CONFUSED:
        return
    lexeme = str(token.get("lexeme") or "") or None

    def words(one: str) -> str:
        return f"{one}:{named(one, pos=pos, lemma=lemma, built=built, lexeme=lexeme)}"

    start, end = int(token.get("start") or 0), int(token.get("end") or 0)
    hard, easy = CONFUSED[code]
    yield Candidate("suffix", segment, start, end, words(code), words(hard), True)
    yield Candidate("suffix", segment, start, end, words(code), words(easy), False)


#: A French noun's gender, as the card names it, by its code.
GENDERS = {"Masc": "Fem", "Fem": "Masc"}

#: A lemma the gender practice asks about: letters, with hyphens between them. Not
#: *km/h*, *m.*, *°c* or *covid-19*, which the tagger calls nouns too (qa on #1278).
_PLAIN_WORD = re.compile(r"^[^\W\d_]+(?:-[^\W\d_]+)*$")

#: Nouns said with either article for a man or a woman (*le* or *la malade*), which "learn
#: this one with its article" would get wrong: not asked (qa on #1278, David 2026-11-16).
#: Nouns in *-iste* are all of this kind and are caught by their ending. A noun whose two
#: genders are two words (*le livre*, *la livre*) is not here: the line's gender is that
#: word's, and its article is the one to learn.
EPICENE = frozenset(
    {
        "adulte", "adversaire", "athlète", "bibliothécaire", "camarade", "capitaine",
        "collègue", "complice", "comptable", "concierge", "élève", "enfant", "gosse",
        "interprète", "juge", "locataire", "malade", "ministre", "partenaire", "philosophe",
        "photographe", "pote", "propriétaire", "psychologue", "responsable", "secrétaire",
        "stagiaire", "fonctionnaire", "libraire", "notaire", "célibataire", "destinataire",
        "dentiste", "domestique", "esclave", "géographe", "biologiste", "astronaute",
        "cinéaste", "diplomate", "économiste", "pédiatre", "psychiatre",
        "sociologue", "spécialiste",
    }
)  # fmt: skip


def gender_candidates(token: Mapping[str, Any], segment: str) -> Iterator[Candidate]:
    """Masculine or feminine, for a French noun the card names a gender for
    (targum-internal#644). The answer is the gender the line gives the noun, and the
    contrast the other one.

    The easy kind is a noun whose ending says its gender and agrees with it, which the card
    says too ("like most nouns in -tion"): the answer carries that ending after a colon,
    `Fem:tion`, for the rule. The hard kind is a noun with no such ending, or one whose
    ending says the other gender (*la plage*, in -age): a word to learn, which is what the
    card leaves unsaid, and what this item asks."""
    from .annotate.endings import ending_of

    if str(token.get("pos") or "") != "NOUN":
        return
    gender = _feats(token.get("feats")).get("Gender", "")
    if gender not in GENDERS:
        return
    lemma = str(token.get("lemma") or token.get("surface") or "")
    plain = lemma.lower()
    if not _PLAIN_WORD.match(lemma) or plain in EPICENE or plain.endswith("iste"):
        return
    told, _, ending = ending_of(lemma).partition(":")
    agrees = bool(ending) and told == gender[0].lower()
    start, end = int(token.get("start") or 0), int(token.get("end") or 0)
    answer = f"{gender}:{ending}" if agrees else gender
    yield Candidate("gender", segment, start, end, answer, GENDERS[gender], not agrees)


def register_candidates(
    text: str, stored: Sequence[Mapping[str, Any]], segment: str
) -> Iterator[Candidate]:
    """Register, for one French line (French's seventh hard spot): read off its words by
    the rules the card uses (`annotate/french_register.py`), so nothing is asked that the
    card does not say.

    A negator said without *ne* is informal, `NeDrop:<the formal clause>` where the rule is
    sure of it, and one said with it is formal, `NeKept`: each is the other's contrast,
    and the dropped one is the hard kind, the one a learner reads as a mistake or misses.
    An *on* the sentence says is "we" is `OnWe`, the hard kind; every other *on* is
    `OnOpen`, "people in general, or 'we' in speech", which is all the rule claims of it."""
    from .annotate.french_register import Word, ne_dropped, ne_kept, ons

    words = [
        Word(
            int(token.get("start") or 0),
            int(token.get("end") or 0),
            str(token.get("surface") or ""),
            str(token.get("pos") or "") or None,
            str(token.get("feats") or "") or None,
        )
        for token in stored
    ]

    def made(at: int, answer: str, contrast: str, hard: bool) -> Candidate:
        return Candidate(
            "register", segment, words[at].start, words[at].end, answer, contrast, hard
        )

    for dropped in ne_dropped(text, words):
        said = f"NeDrop:{dropped.formal}" if dropped.formal else "NeDrop"
        yield made(dropped.negator, said, "NeKept", True)
    for at in ne_kept(text, words):
        yield made(at, "NeKept", "NeDrop", False)
    for one in ons(text, words):
        if one.we:
            yield made(one.at, "OnWe", "OnOpen", True)
        else:
            yield made(one.at, "OnOpen", "OnWe", False)


#: Spots whose answers carry the rule's detail after a colon, so two answers are the same
#: answer when what comes before it is (`_kind`).
_DETAILED = frozenset({"gender", "register"})

#: An item whose question is not its spot's: who an *on* is, on the register spot.
_ASKS = {"OnWe": "practice.ask.on", "OnOpen": "practice.ask.on"}


def _kind(code: str) -> str:
    """What an answer says, less the rule's detail after a colon: `Fem:tion` is `Fem`."""
    return code.partition(":")[0]


def _biblical(folder: Path) -> bool:
    """Whether a built text is scripture, off its own document.json."""
    from .models import is_biblical

    try:
        said = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(said, dict) and is_biblical(said.get("source"))


def _moved_stress(ipa: str) -> str:
    """The same reading with its stress on the next syllable over: the penult where it was
    final, the final where it was anywhere else."""
    from .annotate.pronounce import STRESS_MARK

    bare = ipa.replace(STRESS_MARK, "")
    vowels = "aeiouəɛɔ"
    starts: list[int] = []
    previous = False
    for at, char in enumerate(bare):
        vowel = char in vowels
        if vowel and not previous:
            starts.append(at)
        previous = vowel
    if len(starts) < 2:
        return ""
    stressed_at = ipa.index(STRESS_MARK)
    current = sum(1 for at in starts if at < stressed_at + 1) - 1
    current = max(0, min(current, len(starts) - 1))
    target = len(starts) - 2 if current == len(starts) - 1 else len(starts) - 1
    # The mark goes before the onset consonant, as phonikud writes it.
    vowel_at = starts[target]
    mark_at = vowel_at - 1 if vowel_at > 0 and bare[vowel_at - 1] not in vowels else vowel_at
    return bare[:mark_at] + STRESS_MARK + bare[mark_at:]


def _governed(stored: Sequence[Mapping[str, Any]], segment: str) -> list[Candidate]:
    """The verbs in one segment that take a core preposition here: what the lens lights,
    counted for the ledger (`annotate.governed`)."""
    from .annotate.governed import governed
    from .models import Token

    try:
        tokens = [Token.model_validate(token) for token in stored]
    except ValueError:
        return []
    out = []
    for pair in governed(tokens):
        verb = tokens[pair.verb]
        out.append(
            Candidate("governed", segment, verb.start, verb.end, pair.preposition, "", False)
        )
    return out


@dataclass(frozen=True)
class TextPractice:
    """One built text's candidates per section, and the headword of every word that shares
    its spelling with another word in the text, which is how a homograph item says them."""

    by_section: dict[int, list[Candidate]]
    heads: dict[str, str] = field(default_factory=dict)


def count_text(folder: Path) -> TextPractice | None:
    """Read one built text's candidates off its annotation, uncached."""
    from .coverage import ANNOTATION
    from .models import SegmentedDocument, read_artifact
    from .occurrences import _sections
    from .vocalize.base import has_nikkud, strip_nikkud

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    annotation = folder / ANNOTATION
    if segmented is None or not annotation.is_file():
        return None
    try:
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if segmented.language.split("-")[0] not in REGISTERED:
        return None
    tokens = loaded.get("tokens") or {}
    section_of = _sections(folder, segmented)
    if segmented.language.split("-")[0] == "fr":
        return _french(segmented, tokens, section_of)
    # The vav-consecutive is asked in Biblical text alone, where the spot is claimed.
    scripture = _biblical(folder)
    by_section: dict[int, list[Candidate]] = {}
    spellings: dict[str, dict[str, str]] = {}
    pointed: list[tuple[int, str, int, int, str, str]] = []
    for segment in segmented.segments:
        section = section_of.get(segment.id, 1)
        stored = tokens.get(segment.id) or ()
        by_section.setdefault(section, [])
        # Governed prepositions are declared out of Biblical text (targum-internal#454),
        # so a Biblical text offers none to practise.
        if not scripture:
            by_section[section].extend(_governed(stored, segment.id))
        for token in stored:
            by_section.setdefault(section, []).extend(candidates(token, segment.id))
            word = segment.text[int(token.get("start") or 0) : int(token.get("end") or 0)]
            if scripture:
                by_section[section].extend(vav_candidates(token, word, segment.id))
            # The pronoun on the end, in both registers, Hebrew alone: a Biblical page can
            # switch into Aramaic, which writes its suffixes otherwise.
            if segment.language_in(segmented.language).split("-")[0] == "he":
                by_section[section].extend(suffix_candidates(token, word, segment.id))
            pos = str(token.get("pos") or "")
            lemma = str(token.get("lemma") or "")
            surface = str(token.get("surface") or "")
            if pos in ("PROPN", "PUNCT", "NUM") or not lemma or not surface:
                continue
            bare, _ = strip_nikkud(surface)
            head = str(token.get("headword") or lemma)
            spellings.setdefault(bare, {}).setdefault(lemma, head)
            if has_nikkud(surface):
                pointed.append(
                    (section, segment.id, int(token["start"]), int(token["end"]), bare, lemma)
                )
    homographs = {bare: words for bare, words in spellings.items() if len(words) > 1}
    for section, segment_id, start, end, bare, lemma in pointed:
        words = homographs.get(bare)
        if not words:
            continue
        other = next(word for word in words if word != lemma)
        by_section.setdefault(section, []).append(
            Candidate("homograph", segment_id, start, end, lemma, other, True)
        )
    heads = {lemma: head for words in homographs.values() for lemma, head in words.items()}
    return TextPractice(by_section=by_section, heads=heads)


def _french(
    segmented: Any, tokens: Mapping[str, Any], section_of: Mapping[str, int]
) -> TextPractice:
    """A French text's candidates: the Hebrew spots read DICTA's features and binyanim,
    which a French token does not have, so none of them is asked here."""
    by_section: dict[int, list[Candidate]] = {}
    for segment in segmented.segments:
        found = by_section.setdefault(section_of.get(segment.id, 1), [])
        stored = tokens.get(segment.id) or ()
        for token in stored:
            found.extend(gender_candidates(token, segment.id))
        found.extend(register_candidates(segment.text, stored, segment.id))
    return TextPractice(by_section=by_section)


def text_practice(folder: Path) -> TextPractice | None:
    from .occurrences import _stamp

    stamp = _stamp(folder)
    if stamp is None:
        return None
    return _cached(folder, tuple(stamp))


@lru_cache(maxsize=8)
def _cached(folder: Path, stamp: tuple[int, ...]) -> TextPractice | None:
    cached = folder / CACHE
    if cached.is_file():
        try:
            loaded = json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if (
            isinstance(loaded, dict)
            and loaded.get("version") == VERSION
            and loaded.get("spots") == spots_key()
            and loaded.get("stamp") == list(stamp)
        ):
            return TextPractice(
                by_section={
                    int(section): [
                        Candidate(
                            str(row[0]),
                            str(row[1]),
                            int(row[2]),
                            int(row[3]),
                            str(row[4]),
                            str(row[5]),
                            bool(row[6]),
                        )
                        for row in rows
                    ]
                    for section, rows in (loaded.get("sections") or {}).items()
                },
                heads={str(k): str(v) for k, v in (loaded.get("heads") or {}).items()},
            )
    counted = count_text(folder)
    if counted is None:
        return None
    try:
        write_atomic(
            cached,
            json.dumps(
                {
                    "version": VERSION,
                    "spots": spots_key(),
                    "stamp": list(stamp),
                    "sections": {
                        str(section): [
                            [c.spot, c.segment, c.start, c.end, c.answer, c.contrast, int(c.hard)]
                            for c in rows
                        ]
                        for section, rows in counted.by_section.items()
                    },
                    "heads": counted.heads,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    except OSError:
        pass
    return counted


# -- what a reader has met ---------------------------------------------------------------

FolderFor = Callable[[str], "tuple[Path, str] | None"]


@dataclass(frozen=True)
class Met:
    """A candidate in a line the reader finished, with where to find the text."""

    candidate: Candidate
    document: str
    folder: Path
    section: int
    homographs: Mapping[str, str] = field(default_factory=dict)


def met(
    finished: Iterable[tuple[str, str, int]], folder_for: FolderFor, language: str
) -> Iterator[Met]:
    """Every candidate in a section the reader finished, latest finish first."""
    from .meetings import _finished_folders

    for document, sections, folder in _finished_folders(finished, folder_for, language):
        found = text_practice(folder)
        if found is None:
            continue
        for section in sorted(sections):
            for candidate in found.by_section.get(section, ()):
                heads = found.heads if candidate.spot == "homograph" else {}
                yield Met(candidate, document, folder, section, heads)


@dataclass
class Ledger:
    """How often a reader has met each spot: lines, and the texts they were in."""

    lines: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    def add(self, spot: str, document: str, segment: str) -> None:
        self.lines.setdefault(spot, set()).add((document, segment))

    def encounters(self, spot: str) -> int:
        return len(self.lines.get(spot, ()))

    def texts(self, spot: str) -> int:
        return len({document for document, _ in self.lines.get(spot, ())})

    def ready(self, spot: str) -> bool:
        return self.encounters(spot) >= ENCOUNTERS and self.texts(spot) >= TEXTS


def ledger(found: Iterable[Met]) -> Ledger:
    """The encounter ledger: once per (spot, line), never twice for the same line."""
    out = Ledger()
    for one in found:
        out.add(one.candidate.spot, one.document, one.candidate.segment)
    return out


# -- choosing a round --------------------------------------------------------------------


@dataclass
class State:
    """Where a reader is with one spot: the step on the ramp, when it is next due, the last
    answers (1 right, 0 wrong, newest last) and the lines already asked about."""

    step: int = 0
    due: int = 0
    history: str = ""
    seen: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float | None:
        recent = self.history[-WINDOW:]
        return recent.count("1") / len(recent) if recent else None

    def wants(self) -> bool | None:
        """True for hard items, False for easy, None for both."""
        share = self.accuracy
        if share is None:
            return None
        if share > HIGH:
            return True
        if share < LOW:
            return False
        return None


def line_key(document: str, segment: str) -> str:
    return f"{document}:{segment}"


def choose(
    found: Sequence[Met], state: State, *, count: int = ROUND + 1, seed: int | None = None
) -> list[Met]:
    """A round of items on one spot: never a line already asked about, one item per line,
    hard or easy as the band asks, the first of them the worked example."""
    shuffle = random.Random(seed)
    seen = set(state.seen)
    wanted = state.wants()
    fresh: dict[str, list[Met]] = {}
    for one in found:
        key = line_key(one.document, one.candidate.segment)
        if key in seen:
            continue
        fresh.setdefault(key, []).append(one)
    keys = list(fresh)
    shuffle.shuffle(keys)
    # Lines with an item of the kind the band asks for first; the rest only to fill a
    # round that would otherwise come up short.
    picked: list[Met] = []
    used: set[str] = set()
    for strict in (True, False):
        for key in keys:
            if key in used or len(picked) >= count:
                continue
            options = fresh[key]
            fitting = [one for one in options if wanted is None or one.candidate.hard == wanted]
            if strict and not fitting:
                continue
            picked.append(shuffle.choice(fitting or options))
            used.add(key)
    return picked


def answered(state: State, right: bool, key: str) -> State:
    """The state after one answer."""
    return State(
        step=state.step,
        due=state.due,
        history=(state.history + ("1" if right else "0"))[-WINDOW:],
        seen=[*state.seen, key],
    )


def finished_round(state: State, right: int, asked: int, now: float | None = None) -> State:
    """The state after a round: a step up the ramp for a round mostly right, a step down
    for one mostly wrong, and the next round due by the step."""
    step = state.step
    if asked:
        step = step + 1 if right / asked >= LOW else max(0, step - 1)
    step = min(step, len(INTERVALS) - 1)
    when = int(now if now is not None else time.time()) + INTERVALS[step] * 86400
    return State(step=step, due=when, history=state.history, seen=state.seen)


# -- saying it ---------------------------------------------------------------------------


def said(spot: str, code: str, ui: str, homographs: Mapping[str, str] | None = None) -> str:
    """An answer in words: "past · he", "feminine · plural", "pi'el" (as the card says a
    binyan, in Hebrew), "bound to the next word", "da-VID" as the card spells a sound."""
    from . import strings

    def t(key: str) -> str:
        return strings.text(key, ui)

    if spot == "binyan":
        return code
    if spot == "homograph":
        return (homographs or {}).get(code, code)
    if spot == "stress":
        return plainly(code, ui)
    if spot == "construct":
        return t("practice.construct.bound" if code == "Cons" else "practice.construct.free")
    if spot == "vav":
        return t("reader.grammar.past" if code == "Past" else "reader.grammar.future")
    if spot == "suffix":
        # The card's words, after the code (`suffix_candidates`).
        return code.partition(":")[2] or code
    if spot == "gender":
        return t("reader.grammar.feminine" if _kind(code) == "Fem" else "reader.grammar.masculine")
    if spot == "register":
        return t(
            {
                "NeDrop": "practice.register.informal",
                "NeKept": "practice.register.formal",
                "OnWe": "practice.register.we",
            }.get(_kind(code), "reader.card.on-open")
        )
    feats = _feats(code)
    if spot == "agreement":
        gender = t(
            "reader.grammar.feminine"
            if feats.get("Gender") == "Fem"
            else "reader.grammar.masculine"
        )
        number = t("practice.plural" if feats.get("Number") == "Plur" else "practice.singular")
        return f"{gender} · {number}"
    tense = {"Past": "reader.grammar.past", "Fut": "reader.grammar.future"}.get(
        feats.get("Tense", ""), "reader.grammar.present"
    )
    person = feats.get("Person", "")
    plural = feats.get("Number") == "Plur"
    if person == "1":
        who = t("reader.grammar.we" if plural else "reader.grammar.i")
    elif person == "2":
        who = t("reader.grammar.you")
    elif plural:
        who = t("reader.grammar.they")
    else:
        who = t("reader.grammar.she" if feats.get("Gender") == "Fem" else "reader.grammar.he")
    return f"{t(tense)} · {who}"


#: The rule for each suffix, by its code: the third person by gender and number, the first
#: and second by number.
_SUFFIX_RULES = {
    "3ms": "practice.rule.suffix-3ms",
    "3fs": "practice.rule.suffix-3fs",
    "3mp": "practice.rule.suffix-3mp",
    "3fp": "practice.rule.suffix-3fp",
    "1cs": "practice.rule.suffix-1s",
    "1cp": "practice.rule.suffix-1p",
    "2ms": "practice.rule.suffix-2s",
    "2fs": "practice.rule.suffix-2s",
    "2cs": "practice.rule.suffix-2s",
    "2mp": "practice.rule.suffix-2p",
    "2fp": "practice.rule.suffix-2p",
}

#: The Hebrew each rule names, filled into its blanks here rather than written into the
#: catalogue (design.md §14, line 3; targum-internal#477). The sentence is English or
#: Russian and the letters are not, so the Grammar tab draws each Hebrew run with its own
#: `lang` and `dir` (`ruleText` in grammar.js), and a translation cannot drop or turn one.
_RULE_HEBREW = {
    "practice.rule.bound": {"letter": "ה"},
    "practice.rule.free": {"letter": "ה"},
    "practice.rule.suffix-3ms": {"one": "ו", "two": "יו"},
    "practice.rule.suffix-3fs": {"one": "ה", "two": "יה"},
    "practice.rule.suffix-3mp": {"one": "ם", "two": "הם"},
    "practice.rule.suffix-3fp": {"one": "ן", "two": "הן"},
    "practice.rule.suffix-1s": {"one": "י", "two": "ני"},
    "practice.rule.suffix-1p": {"one": "נו"},
    "practice.rule.suffix-2s": {"one": "ך"},
    "practice.rule.suffix-2p": {"one": "כם", "two": "כן"},
}


def rule(spot: str, code: str, ui: str) -> str:
    """The clause that decided the answer, one line, never a paragraph. Plain text, with
    any Hebrew it names filled in: the page that draws it tags each Hebrew run."""
    from . import strings

    keys = {
        "binyan": "practice.rule.binyan",
        "homograph": "practice.rule.homograph",
        "tense": "practice.rule.tense",
        "agreement": "practice.rule.agreement",
        "construct": "practice.rule.bound" if code == "Cons" else "practice.rule.free",
        "stress": "practice.rule.stress",
        "vav": "practice.rule.vav-past" if code == "Past" else "practice.rule.vav-future",
        "suffix": _SUFFIX_RULES.get(code.partition(":")[0], "practice.rule.suffix-3ms"),
        "gender": _gender_rule(code),
        "register": _REGISTER_RULES.get(_kind(code), "practice.rule.on-open"),
    }
    key = keys[spot]
    if spot == "gender" and code.partition(":")[2]:
        return strings.text(key, ui, ending=code.partition(":")[2])
    if spot == "register" and code.partition(":")[2]:
        return strings.text("practice.rule.ne-dropped", ui, formal=code.partition(":")[2])
    return strings.text(key, ui, **_RULE_HEBREW.get(key, {}))


#: The register rule for each answer; a dropped *ne* with its formal clause is said by
#: `practice.rule.ne-dropped` instead.
_REGISTER_RULES = {
    "NeDrop": "practice.rule.ne-dropped-alone",
    "NeKept": "practice.rule.ne-kept",
    "OnWe": "practice.rule.on-we",
    "OnOpen": "practice.rule.on-open",
}


def _gender_rule(code: str) -> str:
    """The ending, where it told the gender (`gender_candidates`); the word itself, where
    nothing about it does."""
    gender, _, ending = code.partition(":")
    which = "f" if gender == "Fem" else "m"
    return f"practice.rule.gender-{'ending' if ending else 'word'}-{which}"


# How a Hebrew reading is said in letters a learner reads, the way the reader's card says
# it (`plainly` in reader.js, design.md §12, "The card says a Hebrew word in letters you
# read", 2026-10-12). Kept to the same table so a stress item spells a word as its card.
_PLAIN = {
    "en": {
        "χ": "kh", "x": "kh", "ʃ": "sh", "ʒ": "zh", "ʁ": "r", "j": "y", "tʃ": "ch", "dʒ": "j",
        "ʔ": "",
    },
    "ru": {
        "a": "а", "e": "е", "i": "и", "o": "о", "u": "у", "b": "б", "v": "в", "g": "г",
        "d": "д", "h": "х", "z": "з", "χ": "х", "x": "х", "t": "т", "j": "й", "k": "к",
        "l": "л", "m": "м", "n": "н", "s": "с", "f": "ф", "p": "п", "ts": "ц", "tʃ": "ч",
        "dʒ": "дж", "ʒ": "ж", "ʁ": "р", "r": "р", "ʃ": "ш", "w": "в", "ʔ": "",
    },
}  # fmt: skip
_ACUTE = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}


def plainly(ipa: str, ui: str = "en") -> str:
    """`plainly` from reader.js, in Python: syllables with hyphens, the stress an acute."""
    table = _PLAIN.get(ui, _PLAIN["en"])
    cyrillic = table is _PLAIN["ru"]
    words = []
    for word in ipa.split():
        units: list[tuple[str, bool, bool]] = []  # sound, vowel, stressed
        stress = False
        at = 0
        while at < len(word):
            char = word[at]
            if char == "ˈ":
                stress = True
                at += 1
                continue
            two = word[at : at + 2]
            if two in ("ts", "tʃ", "dʒ"):
                units.append((two, False, False))
                at += 2
                continue
            char = {"ɡ": "g", "ə": "e", "ɛ": "e", "ɔ": "o"}.get(char, char)
            if char in "aeiou":
                units.append((char, True, stress))
                stress = False
            elif char.isalpha() or char in "ʃʒʁχʔ":
                units.append((char, False, False))
            at += 1
        vowels = [index for index, unit in enumerate(units) if unit[1]]
        if not vowels:
            continue
        starts = [0]
        for v in range(1, len(vowels)):
            between = vowels[v] - vowels[v - 1] - 1
            starts.append(vowels[v] - between if between < 2 else vowels[v - 1] + 2)
        syllables = []
        for n, start in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(units)
            out = ""
            onset = True
            for sound, vowel, stressed in units[start:end]:
                shown = table.get(sound, sound)
                if vowel:
                    if cyrillic and sound == "e" and onset:
                        shown = "э"
                    if stressed and len(vowels) > 1:
                        shown = shown + "́" if cyrillic else _ACUTE.get(sound, shown)
                if shown:
                    onset = False
                out += shown
            if out:
                syllables.append(out)
        words.append("-".join(syllables))
    return " ".join(word for word in words if word)


# -- the page ----------------------------------------------------------------------------


def state_of(row: Mapping[str, Any] | None) -> State:
    if not row:
        return State()
    return State(
        step=int(row.get("step") or 0),
        due=int(row.get("due") or 0),
        history=str(row.get("history") or ""),
        seen=list(row.get("seen") or []),
    )


def _item(
    one: Met, found: Sequence[Met], ui: str, into: str, *, example: bool, seed: int
) -> dict[str, Any] | None:
    """One item as the page draws it: the line with the word's place, the question, the two
    answers in a stable shuffled order, which is right, the rule, and one real line where
    the other answer is right."""
    from . import strings
    from .meetings import Line, card_line

    candidate = one.candidate
    line = card_line(
        Line(
            "",
            one.document,
            one.folder,
            one.section,
            candidate.segment,
            candidate.start,
            candidate.end,
        ),
        into,
    )
    if line is None or not line.get("word"):
        return None
    right = said(candidate.spot, candidate.answer, ui, one.homographs)
    wrong = said(candidate.spot, candidate.contrast, ui, one.homographs)
    if not right or not wrong or right == wrong:
        return None
    options = [right, wrong]
    random.Random(f"{seed}:{candidate.segment}:{candidate.start}").shuffle(options)
    other = next(
        (
            each
            for each in found
            if (
                _kind(each.candidate.answer) == candidate.contrast
                if candidate.spot in _DETAILED
                else each.candidate.answer == candidate.contrast
            )
            and each.candidate.segment != candidate.segment
            and candidate.spot != "homograph"
        ),
        None,
    )
    contrast = None
    if other is not None:
        drawn = card_line(
            Line(
                "",
                other.document,
                other.folder,
                other.section,
                other.candidate.segment,
                other.candidate.start,
                other.candidate.end,
            ),
            into,
        )
        if drawn:
            contrast = {
                key: drawn[key] for key in ("line", "start", "end", "word", "translation")
            } | {"said": wrong}
    return {
        "key": line_key(one.document, candidate.segment),
        "spot": candidate.spot,
        "example": example,
        "ask": strings.text(_ASKS.get(_kind(candidate.answer), REGISTERED_ASK[candidate.spot]), ui),
        "options": options,
        "answer": options.index(right),
        "said": right,
        "rule": rule(candidate.spot, candidate.answer, ui),
        "hard": candidate.hard,
        "contrast": contrast,
        **{key: line[key] for key in ("line", "start", "end", "word", "translation", "title")},
    }


REGISTERED_ASK = {
    KEYS[name]: practice.ask
    for practices in REGISTERED.values()
    for name, practice in practices.items()
    if practice.ask
}


def page(
    language: str,
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    rows: Mapping[str, Mapping[str, Any]],
    *,
    ui: str = "en",
    into: str = "en",
    spot: str = "",
    now: float | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """What the Grammar tab draws: every spot with its ledger and its schedule, and a round
    on the spot asked for or the one most due. Nothing spends; nothing is written."""
    registered = REGISTERED.get(language, {})
    found = list(met(finished, folder_for, language)) if registered else []
    count = ledger(found)
    at = int(now if now is not None else time.time())
    spots: list[dict[str, Any]] = []
    for name, practice in registered.items():
        key = KEYS[name]
        state = state_of(rows.get(key))
        spots.append(
            {
                "key": key,
                "kind": practice.kind,
                "encounters": count.encounters(key),
                "texts": count.texts(key),
                "ready": count.ready(key),
                "step": state.step,
                "due": state.due,
                "needs": {"encounters": ENCOUNTERS, "texts": TEXTS},
            }
        )
    playable = [one for one in spots if one["ready"] and one["kind"] == "choice"]
    chosen = next((one for one in playable if one["key"] == spot), None)
    if chosen is None and playable:
        chosen = min(playable, key=lambda one: (one["due"] > at, one["due"]))
    round_: dict[str, Any] | None = None
    if chosen is not None:
        key = str(chosen["key"])
        state = state_of(rows.get(key))
        mine = [one for one in found if one.candidate.spot == key]
        mixed = seed if seed is not None else at // 3600
        items: list[dict[str, Any]] = []
        for one in choose(mine, state, seed=mixed):
            item = _item(one, mine, ui, into, example=not items, seed=mixed)
            if item is not None:
                items.append(item)
        round_ = {"spot": key, "items": items, "due": chosen["due"] <= at}
    return {"language": language, "spots": spots, "round": round_}


def record(
    row: Mapping[str, Any] | None,
    *,
    key: str = "",
    right: bool | None = None,
    done: tuple[int, int] | None = None,
    now: float | None = None,
) -> State:
    """The state after one answer (`key`, `right`) or after a round (`done` = right, asked)."""
    state = state_of(row)
    if key and right is not None:
        state = answered(state, right, key)
    if done is not None:
        state = finished_round(state, done[0], done[1], now)
    return state
