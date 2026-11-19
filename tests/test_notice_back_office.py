"""The Privacy Notice and the Data Retention Schedule on the back office, in David's words
(approved word for word on 2026-11-17, design.md §12 "The back office is an overview, a
list of readers and a page each"): clause 3.2 rewritten, the operator's purpose added to
3.6, the active line added to 3.7, and how long an unconfirmed waitlist address is kept."""

from __future__ import annotations

import re
from html import unescape

from targum.render.builder import LEGAL_CHANGED, NOTICE_ALLOWS_LANGUAGES, legal_page


def said(markup: str) -> str:
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


#: Clause 3.2's last sentences, as David approved them.
CLAUSE_3_2 = (
    "The Controller may also see, for each account, how many documents it has "
    "opened and sections it has marked as finished, how many words and phrases it "
    "has marked and how many of those it has marked as known, the dates on which "
    "it did each, whether and when it has signed in, the languages in which it "
    "reads, the credits its requests have used and what they cost the Controller, "
    "and the titles of the documents from the Service's own library which it has "
    "opened or finished; and may write to the Data Subject about their use of the "
    "Service in consequence. The words, phrases and notes themselves, and the "
    "title or source of any material the Data Subject has brought to the Service, "
    "are not shown to the Controller. Legal basis for that processing: Article "
    "6(1)(f), the legitimate interest of the Controller in helping the Data "
    "Subject to make use of the Service. The Data Subject may object in "
    "accordance with clause 7.6."
)
#: Inserted in clause 3.6 after its purposes.
CLAUSE_3_6 = (
    "Also processed for the purpose of showing the Controller, for each account, "
    "how many words were looked up, how long recordings were played and their "
    "pictures shown, how many words were read in sections marked as finished, and "
    "which exercises were practised and how far, each by day and by language; "
    "neither the words looked up nor any segment is so shown. Legal basis for "
    "that processing: Article 6(1)(f), the legitimate interest of the Controller "
    "in helping the Data Subject to make use of the Service. The Data Subject may "
    "object in accordance with clause 7.6. Records erased by the Data Subject, "
    "and records not made because the Data Subject has ceased such recording, are "
    "not shown."
)
#: Appended to clause 3.7's sentence on who returned.
CLAUSE_3_7 = ", and of how many were active on each day and in each language"
#: The schedule's new entry, after the one on "Tell us".
RETENTION = (
    "An address on the waitlist not confirmed. Thirty days from the request to "
    "join, whereupon the address, and any link tried on the front page with it, "
    "is deleted."
)


def test_the_notice_is_dated_the_day_it_changed() -> None:
    assert LEGAL_CHANGED == "19 November 2026"


def test_clause_3_2_says_what_the_operator_sees_word_for_word() -> None:
    page = said(legal_page("privacy"))
    assert "Legal basis: Article 6(1)(b). " + CLAUSE_3_2 + " Material uploaded" in page
    assert "the words, phrases, notes and titles themselves are not shown" not in page


#: Clause 3.6's own basis and the way out of its recording, which stay with its own
#: purposes (David, 2026-11-18: "Yes, move it").
CLAUSE_3_6_OWN = (
    "Legal basis: Article 6(1)(b). The Data Subject may at any time cease such recording,"
    " and erase the records held, from the account page."
)


def test_clause_3_6_adds_the_operators_purpose_after_its_own() -> None:
    """The operator's purpose, with its own basis, comes after 3.6's purposes and their
    basis, so 6(1)(b) is never read as the basis of the operator's view."""
    page = said(legal_page("privacy"))
    assert (
        "the texts the Service suggests to the Data Subject. "
        + CLAUSE_3_6_OWN
        + " "
        + CLAUSE_3_6
        + " Aggregate records of use."
    ) in page
    assert page.count("Also processed for the purpose of showing the Controller") == 1


def test_clause_3_7_counts_who_was_active() -> None:
    page = said(legal_page("privacy"))
    assert "marked a word and returned on another day" + CLAUSE_3_7 + ". Processed" in page


def test_the_schedule_deletes_an_unconfirmed_address_after_thirty_days() -> None:
    page = said(legal_page("retention"))
    tell_us = page.index('A message sent by means of "Tell us".')
    entry = page.index(RETENTION)
    assert tell_us < entry < page.index("A fault report sent by a browser.")


def test_the_languages_are_allowed_by_the_same_change_that_says_so() -> None:
    """The back office's languages (the Readers column, the Overview's row) read this
    switch, and it is on only where 3.2 and 3.7 say the languages are shown."""
    page = said(legal_page("privacy"))
    assert NOTICE_ALLOWS_LANGUAGES is True
    assert "the languages in which it reads" in page
    assert "active on each day and in each language" in page
