"""The words a dictionary is worst at, written out by hand once.

Strong's is a good gloss for a noun and a poor one for a particle. Its entry for `דִּי`
— the commonest word in Daniel's Aramaic, 272 occurrences in the books measured — is a
paragraph beginning "that, used as relative conjunction, and especially (with a
preposition) in adverbial phrases", and its entry for `אֵת`, the direct-object marker
and the commonest word in the Hebrew Bible, is the sentence "[as such unrepresented in
English]". Neither is what a learner wants on a card.

They are also a closed set, which is what makes this worth writing rather than buying.
Counted over 39 books of the scripture shelf with the content words already glossed from
the lexicon, everything still without a meaning came to **174 Hebrew forms and 63
Aramaic ones** — and the top ten Hebrew forms are half of all of it. Written once here,
they are right in every text on the shelf for ever, and cost nothing.

**Keyed by lexeme number, not by spelling.** `לֹא` is `3808` in Hebrew and `3809` in
Aramaic; `אֵת` is `853` the object marker and `854` the preposition "with", and both are
spelled the same. A number says which word this is where no spelling can. The handful of
pieces the tagging numbers with a letter rather than a number — the pronominal suffixes,
`־ךָ` and `־הֶם` and the rest — are keyed by their written form instead, in `BY_FORM`.

**House style**: short, lower case, senses separated by a semicolon, the way the bought
glosses read. A grammatical note goes in brackets where the word does a job English does
not have a word for.
"""

from __future__ import annotations

#: Hebrew, by Strong's number. Ordered as the corpus orders them, commonest first, so
#: the top of this list is the part that matters and the bottom is the tail.
HEBREW: dict[str, str] = {
    "853": "[marks the direct object]",
    "5921": "on; over; against; concerning",
    "413": "to; toward; into",
    "834": "which; that; who",
    "3808": "not; no",
    "3588": "for; because; that; when",
    "1931": "he; it; that",
    "5704": "until; as far as; while",
    "4480": "from; out of; than",
    "2088": "this",
    "859": "you",
    "518": "if; whether; when",
    "5973": "with; beside",
    "854": "with; near",
    "589": "I",
    "2009": "behold; here is",
    "369": "there is not; nothing",
    "370": "where?; from where?",
    "4100": "what?; how?; why?",
    "428": "these",
    "408": "do not; let there not be",
    "1571": "also; even; moreover",
    "310": "after; behind; afterwards",
    "2063": "this [f.]",
    "1992": "they",
    "8478": "under; beneath; instead of",
    "3651": "so; thus; therefore",
    "4310": "who?",
    "996": "between; among",
    "4994": "please; now [softens a request]",
    "595": "I",
    "176": "or",
    "2005": "behold; if",
    "4616": "so that; for the sake of",
    "5048": "before; opposite; in front of",
    "3644": "like; as",
    "3426": "there is; there are",
    "6435": "lest; so that not",
    "587": "we",
    "7535": "only; except",
    "1115": "not; without; except",
    "1157": "behind; through; on behalf of",
    "3282": "because; on account of",
    "349": "how?; how!",
    "5542": "selah [a musical or liturgical mark]",
    "1077": "not",
    "4069": "why?",
    "681": "beside; near",
    "1945": "woe!; ah!",
    "346": "where?",
    "2007": "they [f.]",
    "5978": "with; beside",
    "4970": "when?",
    "4136": "opposite; in front of",
    "335": "where?; which?",
    "1097": "without; not",
    "188": "woe!; alas!",
    "3863": "if only; were it that",
    "5227": "in front of; straight ahead",
    "2486": "far be it!; God forbid",
    "1107": "apart from; besides",
    "2108": "except; besides",
    "2098": "this; which",
    "162": "ah!; alas!",
    "3884": "if not; unless",
    "577": "please!; I beg you",
    "1889": "aha!",
    "994": "please; pardon me",
    "2090": "this",
    "375": "where?",
    "575": "where?; when?",
    "1119": "in; with",
    "411": "these",
    "1975": "this; that one",
    "336": "not; where?",
    "339": "woe!; alas!",
    "1976": "this one; that one",
    "5168": "we",
}

#: Aramaic, by Strong's number. A separate table because the words are separate: Hebrew
#: `לֹא` is 3808 and Aramaic `לָא` is 3809, and a reader of Daniel meeting `דִּי` is not
#: meeting a Hebrew word at all.
ARAMAIC: dict[str, str] = {
    "1768": "that; which; who; of",
    "4481": "from; out of; by",
    "5922": "on; over; concerning",
    "3809": "not; no",
    "1836": "this",
    "6925": "before; in front of",
    "5705": "until; as far as",
    "6903": "because; corresponding to; before",
    "3606": "all; every; whole",
    "5974": "with",
    "2006": "if; whether",
    "576": "I",
    "383": "there is; there are",
    "1932": "he; it",
    "479": "those",
    "607": "you",
    "1791": "this; that",
    "1994": "them",
    "4479": "who?",
    "4101": "what?; why?",
    "3860": "therefore; but; except",
    "459": "these",
    "1668": "this [f.]",
    "1297": "but; nevertheless",
    "586": "we",
    "637": "also; moreover",
    "718": "behold!",
    "8460": "under; beneath",
    "431": "behold!",
    "581": "they",
    "1797": "that; the same",
    "1887": "behold!",
    "608": "you [pl.]",
    "3487": "[marks the direct object]",
    "870": "place; after",
    "3890": "to; toward",
    "3964": "what?",
    "2370": "behold!",
    # The Aramaic twins of Hebrew words, which Strong numbered separately.
    "409": "do not",
    "311": "after; behind",
    "5049": "before; opposite",
    "997": "between",
}

#: The pieces the tagging numbers with a letter rather than a number: the pronominal
#: suffixes, which are not lexemes of their own and so have nothing to key on but their
#: spelling. Shared between the two languages, which write them nearly alike.
#:
#: These are the pieces left standing as the word where nothing else in it is numbered —
#: `בּוֹ` is a preposition and a suffix and the suffix is what it means. A gloss here is
#: the pronoun, since that is what the reader is looking at.
BY_FORM: dict[str, str] = {
    "ו": "him; his; it",
    "ך": "you; your",
    "י": "me; my",
    "הם": "them; their",
    "כם": "you; your [pl.]",
    "נו": "us; our",
    "ם": "them; their",
    "ה": "her; it",
    "מו": "them; their",
    "הן": "them; their [f.]",
    "כה": "you; your [f.]",
    "הון": "them; their",
    "כון": "you; your [pl.]",
    "נא": "us; our",
}


def gloss_for(lexeme: str | None, form: str) -> str:
    """The hand-written gloss for one closed-class word, or "" where there is none.

    By number where the tagging gave one, by spelling where it gave a letter. The two
    language tables are asked together and need no flag between them: Strong numbered
    the whole lexicon once, so `3808` is the Hebrew `לֹא` and `3809` the Aramaic `לָא`
    and no number means two things.
    """
    number = (lexeme or "").strip().split(" ")[0].lstrip("H")
    if number:
        for table in (HEBREW, ARAMAIC):
            if number in table:
                return table[number]
    return BY_FORM.get(form, "")
