"""French register: *ne* dropped from a negation, and *on* for *nous*. French's seventh
hard spot in `stages.HARD_SPOTS`.

Spoken French drops the *ne* of a negation (*je sais pas* for *je ne sais pas*) and says
*on* where writing says *nous* (*on y va*, *nous, on est contents*). A learner taught on
the written language meets both in every film and every line of dialogue and reads them
as mistakes, or does not see the negation at all. They are register, not errors (David's
D5, 2026-11-05): the card says which register a line is in and what the formal one says,
and corrects nothing.

**Rules, not a model.** Both are read off the words as written, with the tagger's part of
speech used only to refuse: a negator the tagger calls a noun (*un pas*, *une personne*)
is not one. The same rule runs on the page and in `scripts/eval_register.py`, which scores
it on ling-fr's own gold (`evals/french-register-gold.jsonl`) with no tags at all, so the
number measured is the rule's and the page can only say less than it.

*Ne* dropped: a negator (*pas*, *jamais*, *rien*, *plus*, *personne*, *guère*) after a
subject pronoun and its verb, with no *ne* or *n'* in the clause before it. Only the first
in a clause is named (*j'ai jamais rien vu* drops one *ne*). What it misses, by design: a
noun subject (*mon frère vient pas*) and an imperative (*fais pas ça*), where the rule
cannot tell the verb without a parse, and *plus* wherever it could be "more" (*j'ai plus
faim*). It says nothing it is not sure of.

*On* for *nous*: *on* is always a subject, and as often "people" or "someone" as "we", so
the card says "we" only where the sentence says so: *nous* right before it, agreement in
the plural (*on est partis*), *ensemble* or *tous les deux*, *toi et moi*, *chez nous*, a
suggestion (*et si on allait…?*), and the fixed *on y va*. Every other *on* gets the open
line, "people in general, or 'we' in speech".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: Words that close a negation opened by *ne*.
NEGATORS = frozenset({"pas", "jamais", "rien", "plus", "personne", "guère"})

#: Subject pronouns, strongest first: *nous*, *vous* and the spoken *t'* (*t'as vu*) are
#: subjects only where nothing stronger is in the clause, because they are objects as
#: often (*il vous connaît*, *il t'a vu*).
SUBJECTS = ("je", "j'", "tu", "il", "elle", "on", "ils", "elles", "ça", "c'", "ce", "ç'")
WEAK_SUBJECTS = ("nous", "vous", "t'")

#: Words that open a new clause, so a *ne* or a subject before them is not this clause's.
OPENERS = frozenset(
    {
        "que",
        "qu'",
        "qui",
        "mais",
        "et",
        "ou",
        "car",
        "parce",
        "quand",
        "si",
        "lorsque",
        "lorsqu'",
        "comme",
        "puisque",
        "puisqu'",
        "donc",
        "où",
        "dont",
        "quoique",
        "quoiqu'",
    }
)

#: What a negator cannot follow and still be one: a determiner makes it a noun (*un pas*,
#: *une personne*), and these set phrases are not negation at all (*de rien*, *à jamais*,
#: *si jamais*, *non plus*, *le plus*, *sans rien*, *pour rien*).
NOT_AFTER = frozenset(
    {
        "un",
        "une",
        "le",
        "la",
        "les",
        "l'",
        "des",
        "du",
        "de",
        "d'",
        "ce",
        "cet",
        "cette",
        "ces",
        "mon",
        "ton",
        "son",
        "ma",
        "ta",
        "sa",
        "mes",
        "tes",
        "ses",
        "notre",
        "votre",
        "leur",
        "nos",
        "vos",
        "leurs",
        "chaque",
        "quelque",
        "aucun",
        "aucune",
        "à",
        "au",
        "aux",
        "en",
        "pour",
        "sans",
        "si",
        "non",
        "que",
        "qu'",
        "moi",
        "toi",
        "lui",
        "eux",
    }
)

#: What *plus* is followed by when it is "no more" and could not be "more": the end of the
#: clause, another negator, or an object pronoun (*je veux plus te voir*).
PLUS_BEFORE = frozenset(
    {"rien", "personne", "jamais", "aucun", "aucune", "guère", "te", "me", "se", "t'", "m'", "s'"}
    | {"lui", "y", "en", "nous", "vous"}
)

#: What ends a clause between two words.
BREAK = re.compile(r"[,;:()—–\"«»?!.…\[\]]")

#: A part of speech that makes a negator not one.
NOT_NEGATOR_POS = frozenset({"NOUN", "PROPN", "ADJ"})

#: Forms of *être* after which the plural says who *on* is (*on est partis*).
ETRE = frozenset(
    {"est", "était", "sera", "serait", "soit", "fut", "été", "étaient", "êtes", "sommes"}
)
#: Words passed over between *être* and its agreeing word.
BETWEEN = frozenset(
    {
        "pas",
        "plus",
        "jamais",
        "bien",
        "très",
        "tous",
        "toutes",
        "déjà",
        "encore",
        "vraiment",
        "trop",
        "si",
        "tellement",
        "toujours",
        "été",
        "tout",
        "assez",
        "un",
        "peu",
        "ne",
        "n'",
    }
)
#: Words ending in -s or -x that are singular, or invariable, after *être*.
SINGULAR_S = frozenset(
    {
        "pris",
        "mis",
        "assis",
        "surpris",
        "gros",
        "bas",
        "las",
        "heureux",
        "précis",
        "compris",
        "promis",
        "soumis",
        "permis",
        "admis",
        "acquis",
        "conquis",
        "épris",
        "appris",
        "repris",
        "dans",
        "dès",
        "sous",
        "très",
        "plus",
        "moins",
        "jamais",
        "toujours",
        "mieux",
        "mauvais",
        "frais",
        "gris",
        "français",
        "anglais",
        "sérieux",
        "curieux",
        "nerveux",
        "jaloux",
        "vieux",
        "doux",
        "faux",
        "épais",
        "chez",
        "après",
        "depuis",
        "alors",
        "ailleurs",
        "parmi",
        "vers",
        "malgré",
        "fois",
        "temps",
        "pas",
        "tous",
        "toutes",
        "ans",
        "mois",
        "jours",
        "heures",
        "minutes",
        "gens",
        "bras",
        "corps",
        "prix",
        "choix",
        "voix",
        "dos",
        "nez",
        "assez",
        "puis",
        "trois",
        "deux",
        "six",
        "dix",
        "jus",
        "confus",
        "inclus",
        "exclus",
        "obtus",
        "ras",
        "clos",
    }
)
#: Set phrases that say "we" wherever *on* is in them.
TOGETHER = (
    ("ensemble",),
    ("tous", "les", "deux"),
    ("toutes", "les", "deux"),
    ("tous", "les", "trois"),
    ("toutes", "les", "trois"),
    ("chez", "nous"),
    ("entre", "nous"),
    ("nous-mêmes",),
    ("nous", "autres"),
    ("toi", "et", "moi"),
    ("et", "moi"),
    ("moi", "et"),
)
#: What *on* says "we" in, said right after it: *on y va*, *on se voit demain*.
FIXED_AFTER = (
    ("y", "va"),
    ("s'", "en", "va"),
    ("se", "voit"),
    ("se", "revoit"),
    ("se", "retrouve"),
    ("se", "tutoie"),
)


@dataclass(frozen=True)
class Word:
    """What the rules read of a word: where it is in the text, how it is written, and the
    tagger's part of speech where there is one."""

    start: int
    end: int
    surface: str
    pos: str | None = None


@dataclass(frozen=True)
class NeDropped:
    """A negation said without its *ne*: the negator's index, the clause's subject's, and
    the formal clause from the subject to the negator (*je ne sais pas*)."""

    negator: int
    subject: int
    formal: str


@dataclass(frozen=True)
class On:
    """An *on*, by index, and whether the sentence says it is "we"."""

    at: int
    we: bool


def norm(surface: str) -> str:
    """A word as the rules compare it: lowercase, one apostrophe, and the hyphen of an
    inverted pronoun taken off (*-t-on*, *-ce*)."""
    said = surface.lower().replace("’", "'").strip()
    if said.startswith("-t-"):
        said = said[3:]
    return said.lstrip("-")


def _ne(said: str) -> bool:
    return said in ("ne", "n'") or (said.startswith("n'") and len(said) > 2)


def _broken(text: str, before: Word, after: Word) -> bool:
    return bool(BREAK.search(text[before.end : after.start]))


def _clause_start(text: str, words: Sequence[Word], at: int) -> int:
    """The first word of the clause the word at `at` stands in."""
    start = at
    while start > 0:
        if _broken(text, words[start - 1], words[start]):
            break
        said = norm(words[start - 1].surface)
        # *s'* is *si* before *il* and *ils*, and *se* everywhere else.
        if said in OPENERS or (said == "s'" and norm(words[start].surface) in ("il", "ils")):
            break
        start -= 1
    return start


def _is_negator(text: str, words: Sequence[Word], at: int) -> bool:
    said = norm(words[at].surface)
    if said not in NEGATORS:
        return False
    if words[at].pos in NOT_NEGATOR_POS:
        return False
    if at > 0 and norm(words[at - 1].surface) in NOT_AFTER:
        return False
    if said == "plus":
        last = at + 1 >= len(words) or _broken(text, words[at], words[at + 1])
        if not last and norm(words[at + 1].surface) not in PLUS_BEFORE:
            return False
    return True


def _subject(words: Sequence[Word], start: int, at: int) -> int | None:
    """The clause's subject pronoun before the negator, with a word (its verb) between."""
    for choices in (SUBJECTS, WEAK_SUBJECTS):
        for index in range(start, at - 1):
            if norm(words[index].surface) in choices:
                return index
    return None


#: A subject written elided, as it is written before *ne*.
_UNELIDED = {"j'": "je", "c'": "ce", "ç'": "ça", "t'": "tu"}


def _elided(word: str) -> bool:
    return bool(word) and word[0].lower() in "aeiouyhàâäéèêëîïôöùûü"


def _formal(text: str, words: Sequence[Word], subject: int, negator: int) -> str:
    """The clause from its subject to the negator, with the *ne* put back after the
    subject: *j'ai jamais* → *je n'ai jamais*, *c'est pas* → *ce n'est pas*."""
    head = words[subject]
    said = text[head.start : head.end]
    apostrophe = "’" if "’" in text else "'"
    whole = _UNELIDED.get(norm(said))
    if whole:
        said = whole.capitalize() if said[0].isupper() else whole
    rest = text[head.end : words[negator].end].lstrip()
    ne = f"n{apostrophe}" if _elided(rest) else "ne "
    return f"{said} {ne}{rest}"


def ne_dropped(text: str, words: Sequence[Word]) -> list[NeDropped]:
    """Every clause in `text` that negates without *ne*, at its first negator."""
    out: list[NeDropped] = []
    seen: set[int] = set()
    for at in range(len(words)):
        if not _is_negator(text, words, at):
            continue
        start = _clause_start(text, words, at)
        if start in seen:
            continue
        before = [norm(word.surface) for word in words[start:at]]
        if any(_ne(said) for said in before):
            seen.add(start)
            continue
        subject = _subject(words, start, at)
        if subject is None:
            continue
        seen.add(start)
        out.append(NeDropped(at, subject, _formal(text, words, subject, at)))
    return out


def _has(said: Sequence[str], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    return any(tuple(said[i : i + size]) == phrase for i in range(len(said) - size + 1))


def _plural_after(text: str, words: Sequence[Word], at: int) -> bool:
    """Whether *on* at `at` is followed, in its clause, by *être* and a word in the
    plural: *on est partis*, *on était tous fatigués*."""
    index = at + 1
    reached = False
    while index < len(words) and index <= at + 6:
        if _broken(text, words[index - 1], words[index]):
            return False
        said = norm(words[index].surface)
        if said in ETRE:
            reached = True
        elif reached and said not in BETWEEN:
            plural = said.endswith(("s", "x")) and len(said) > 2 and said not in SINGULAR_S
            return plural and words[index].pos not in ("NOUN", "PROPN", "ADP", "DET")
        elif not reached and said not in (
            "a",
            "avait",
            "aura",
            "aurait",
            "ne",
            "n'",
            "y",
            "s'",
            "se",
        ):
            return False
        index += 1
    return False


def ons(text: str, words: Sequence[Word]) -> list[On]:
    """Every *on* in `text`, and whether the sentence says it means "we"."""
    said = [norm(word.surface) for word in words]
    whole = text.strip()
    out: list[On] = []
    for at, one in enumerate(said):
        if one != "on":
            continue
        we = (
            (at > 0 and said[at - 1] == "nous")
            or any(_has(said, phrase) for phrase in TOGETHER)
            or any(tuple(said[at + 1 : at + 1 + len(p)]) == p for p in FIXED_AFTER)
            or _plural_after(text, words, at)
            or (
                at > 0
                and said[at - 1] == "si"
                and whole.endswith("?")
                and at + 1 < len(said)
                and said[at + 1].endswith(("ait", "aient"))
            )
        )
        out.append(On(at, we))
    return out


def lines(text: str, words: Sequence[Word]) -> dict[int, str]:
    """The grammar-line additions for one French segment, by word index: `Reg=NeDrop` and
    `Formal=…` on a negator said without *ne*, `On=We` or `On=Open` on each *on*."""
    out: dict[int, str] = {}
    for found in ne_dropped(text, words):
        out[found.negator] = f"Reg=NeDrop|Formal={found.formal.replace('|', ' ')}"
    for one in ons(text, words):
        out[one.at] = "On=We" if one.we else "On=Open"
    return out


#: Words the eval's tokenizer splits off at the apostrophe. The page has the tagger's
#: tokens, which split the same way (`annotate/model_lemma.py`).
_ELIDING = r"(?:jusqu|lorsqu|puisqu|quoiqu|qu|[ljmtscndç])['’]"
_WORD = re.compile(rf"(?i)\b{_ELIDING}|[\w]+(?:[-'’][\w]+)*|-[\w]+")


def words_of(text: str) -> list[Word]:
    """A sentence cut into words with no tagger: what `scripts/eval_register.py` scores."""
    out: list[Word] = []
    for found in _WORD.finditer(text):
        piece = found.group(0)
        start = found.start()
        # Inversion: *sait-on*, *est-ce*, *va-t-il* say the pronoun as its own word.
        inverted = re.search(r"-(?:t-)?(on|il|elle|ils|elles|ce|je|tu|nous|vous)$", piece, re.I)
        if inverted and inverted.start() > 0:
            out.append(Word(start, start + inverted.start(), piece[: inverted.start()]))
            out.append(Word(start + inverted.start(), found.end(), piece[inverted.start() :]))
        else:
            out.append(Word(start, found.end(), piece))
    return out
