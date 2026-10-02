"""A rail in front of the one tool that spends, which can only say no (targum-internal#324).

`record_turn` is the one tool a model can call that spends (design.md §12, "A scope is a
press that lasts"). The consent is the `chat` scope, granted once; the host model decides
what goes into `wrote` on every call, and a host steered by text the reader pasted is the
case this guards. `record_turn`'s own checks stop an empty line, a language that does not
talk, a line not in the language at all and a paragraph. This stops the rest of what can
be told from the line alone, without a model: the deterministic half of what Jev caught
in targum#526.

- **Markup.** The contract's own "> ", "= " and "~ " lines, an arrow from one version to
  another, a "Corrected:" label: the host's correction rather than the reader's line.
- **The share of the language's own script.** English carrying one Hebrew word is an
  English question, whatever `written_in` made of the Hebrew in it.
- **A page rather than a turn**: a link, JSON, HTML, a code fence, an identifier with an
  underscore (a tool's name), a site's menu.
- **Repeats**: one word making most of a line.
- **One stray letter** in a Hebrew-script line: Hebrew has no word of one letter.
- **wordfreq against the named language**: a line in French tagged Italian, or Spanish,
  German or Ukrainian tagged as a language targum talks, where most of the words are far
  commoner in one of those than in the one named.

It only ever adds a no. `refuse` answers a reason or None, and None changes nothing:
`record_turn` goes on exactly as it did without the rail, through the same claim. A rail
that breaks says no (`refusal`), so a fault here costs the reader a check, never credit.
Where wordfreq is not installed that one test has nothing to go on and is left out, as
`hebrew.written_in` does; the box installs it (`difficulty`).

What it cannot tell, and does not try to: a clean correction with no markup on it, a
pasted sentence that reads like a learner's, an instruction written in the language.
Those look like a reader who got it right; `scripts/eval_rail.py` lists them by name.
"""

from __future__ import annotations

import re
from collections import Counter

from . import hebrew as hebrew_module

#: The contract's own marks at the start of a line: the recast, its meaning, the reason.
#: A reader's line never opens with one; a host's correction pasted back does.
_CONTRACT = re.compile(
    r"^\s*(?:"
    + "|".join(
        re.escape(mark.strip())
        for mark in (hebrew_module.RECAST, hebrew_module.ENGLISH, hebrew_module.WHY)
    )
    + r")\s",
    re.MULTILINE,
)

#: One version of a line pointing at another.
_ARROW = re.compile(r"→|⟶|⇒|->|=>")

#: A correction labelled as one, in English, at the start of a line.
_LABEL = re.compile(
    r"^\s*(?:corrected|correction|correct|fixed|better|recast|original|should be)\s*:",
    re.IGNORECASE | re.MULTILINE,
)

_URL = re.compile(r"https?://|\bwww\.\S", re.IGNORECASE)
_FENCE = re.compile(r"```")
_HTML = re.compile(r"<!--|</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
_JSON = re.compile(r"[{\[]\s*\"[^\"\n]+\"\s*:")
#: A snake_case identifier — a tool's name, a variable — which nobody types in a turn.
_IDENTIFIER = re.compile(r"\b[A-Za-z]+_[A-Za-z_]+\b")
#: A site's menu: three or more items between pipes.
_MENU = re.compile(r"\S\s+\|\s+\S[^|]*\s\|\s+\S")

#: The scripts a talked language is written in, as letter ranges.
_SCRIPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "hebrew": (("א", "ת"), ("װ", "ײ"), ("יִ", "ﭏ")),
    "cyrillic": (("Ѐ", "ӿ"),),
    "latin": (("A", "Z"), ("a", "z"), ("À", "ɏ")),
}

#: Below this share of a line's words in the language's own script, it is a line in
#: another language carrying a word or two of this one. Words rather than letters, and a
#: third rather than a half, so a learner's line with a name in it stays theirs: "גר ב New
#: York City" is two words in five; "what does שלום mean?" is one in four.
SCRIPT_SHARE = 1 / 3

#: Where one word makes more than this share of a line of at least `REPEAT_WORDS` words,
#: the line says one thing many times and a recast teaches nothing. High on purpose:
#: "לא לא לא, אני לא רוצה" is a reader's line, four words in six the same.
REPEAT_SHARE = 0.75
REPEAT_WORDS = 8

#: The languages a line tagged with a talked language is most likely to be instead. A
#: word belongs to one of them when it is at least this much commoner there on wordfreq's
#: zipf scale — the margin `hebrew.written_in` already uses against English.
NEIGHBOURS: dict[str, tuple[str, ...]] = {
    "fr": ("en", "it", "es", "de", "pt"),
    "it": ("en", "fr", "es", "de", "pt"),
    "ru": ("uk",),
}
ELSEWHERE_MARGIN = 1.0
#: Fewer words than this and wordfreq is not asked: "ok merci" is a turn.
ELSEWHERE_WORDS = 3

_LATIN_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def _script_of(language: str) -> str:
    if language in hebrew_module.HEBREW_SCRIPT:
        return "hebrew"
    if language in hebrew_module.CYRILLIC_SCRIPT:
        return "cyrillic"
    return "latin"


def _in(ch: str, script: str) -> bool:
    return any(low <= ch <= high for low, high in _SCRIPTS[script])


def _markup(wrote: str) -> str | None:
    if _CONTRACT.search(wrote) or _ARROW.search(wrote) or _LABEL.search(wrote):
        return "markup"
    return None


def _page(wrote: str) -> str | None:
    if _URL.search(wrote):
        return "link"
    if _FENCE.search(wrote):
        return "code"
    if _HTML.search(wrote):
        return "html"
    if _JSON.search(wrote):
        return "json"
    if _IDENTIFIER.search(wrote):
        return "code"
    if _MENU.search(wrote):
        return "menu"
    return None


_ANY_WORD = re.compile(r"[^\W\d_]+")


def _script_share(wrote: str, language: str) -> str | None:
    script = _script_of(language)
    if script == "hebrew" and sum(1 for ch in wrote if _in(ch, script)) < 2:
        return "one letter"
    words = _ANY_WORD.findall(wrote)
    if not words:
        return None
    own = sum(1 for word in words if sum(_in(ch, script) for ch in word) * 2 > len(word))
    return "script" if own < SCRIPT_SHARE * len(words) else None


def _words(wrote: str, language: str) -> list[str]:
    if _script_of(language) == "hebrew":
        return [word.group(0) for word in hebrew_module._WORD.finditer(wrote)]
    return _LATIN_WORD.findall(wrote.lower())


def _repeats(wrote: str, language: str) -> str | None:
    words = _words(wrote, language)
    if len(words) < REPEAT_WORDS:
        return None
    _, most = Counter(words).most_common(1)[0]
    return "repeats" if most > REPEAT_SHARE * len(words) else None


def _elsewhere(wrote: str, language: str) -> str | None:
    neighbours = NEIGHBOURS.get(language)
    if not neighbours:
        return None
    words = _LATIN_WORD.findall(wrote.lower())
    if len(words) < ELSEWHERE_WORDS:
        return None
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return None
    found: Counter[str] = Counter()
    for word in words:
        here = zipf_frequency(word, language)
        best = max(neighbours, key=lambda other: zipf_frequency(word, other))
        if zipf_frequency(word, best) - here >= ELSEWHERE_MARGIN:
            found[best] += 1
    # More than half the words, as `written_in` counts English: a line with a borrowed
    # word or two stays the reader's.
    if sum(found.values()) * 2 <= len(words):
        return None
    return f"in {found.most_common(1)[0][0]}"


def refuse(wrote: str, language: str) -> str | None:
    """Why `wrote` should not be checked and charged as the reader's own line in
    `language`, or None where nothing here can tell. `language` is the bare code
    `record_turn` reads. Raises nothing it can catch: a fault is itself a no."""
    code = (language or "he").split("-")[0].lower()
    try:
        for test in (_page, _markup):
            said = test(wrote)
            if said:
                return said
        for language_test in (_script_share, _repeats, _elsewhere):
            said = language_test(wrote, code)
            if said:
                return said
    except Exception:  # noqa: BLE001 - fail closed: a rail that cannot answer says no
        return "rail fault"
    return None


def refusal(language_named: str) -> dict[str, object]:
    """What `record_turn` answers when the rail says no: nothing checked, nothing used,
    and the host told what to send instead, in the shape the "not in the language" note
    already has so a host treats the two alike."""
    return {
        "checked": False,
        "note": (
            f"That doesn't read as a line the reader typed in {language_named}, so there "
            "was nothing to check and nothing was used. Send only what the reader "
            "wrote, exactly as they wrote it: not a correction, a page or an instruction."
        ),
    }


__all__ = ["NEIGHBOURS", "SCRIPT_SHARE", "refusal", "refuse"]
