"""The Privacy Notice and the Data Retention Schedule on paying through Paddle, in David's
words (approved word for word on 2026-11-17; targum-internal#59 phase 2): the payment
clause, Paddle as a recipient in its own right, its checkout on the plans page, the
transfer to the United Kingdom, the cookie sentence, and the retention of payment records
and of Paddle's notifications."""

from __future__ import annotations

import re
from html import unescape

import pytest

from targum.render.builder import LEGAL_CHANGED, legal_page


def said(markup: str) -> str:
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def test_the_notice_is_dated_the_day_david_approved_it() -> None:
    assert LEGAL_CHANGED == "17 November 2026"


PRIVACY = [
    "Payment. Where the Data Subject pays for a plan or for further credits, the sale is"
    " made to the Data Subject by Paddle.com Market Limited, as stated at clause 4.3, and"
    " the Controller receives no card, bank or postal details and no sum of money. The"
    " Controller keeps the following: the plan; whether it is paid monthly or every three"
    " months; its status as last reported by Paddle; the day upon which the period paid"
    " for ends; whether the Data Subject has cancelled it so that it ends upon that day;"
    " the time at which a renewal first failed; the periods for which each plan was paid;"
    " the identifiers which Paddle assigns to the Data Subject as its customer and to each"
    " subscription, with the time at which Paddle reported a subscription cancelled; for"
    " each purchase of further credits, the number of credits, the time of the purchase"
    " and Paddle's identifier of the transaction. The Controller further records, for each"
    " notification received from Paddle, its identifier, its kind and the time of its"
    " receipt, which bear no account. Before each purchase the Controller gives Paddle the"
    " number of the Data Subject's account and a code derived from it, by which Paddle's"
    " notifications are matched to the account. Processed for the purposes of providing"
    " the plan and the credits paid for, holding the Data Subject to the allowance of"
    " their plan, and cancelling the plan upon the closure of the account. Legal basis:"
    " Article 6(1)(b).",
    "Where the Data Subject pays for a plan or for further credits, Paddle.com Market"
    " Limited (United Kingdom) sells them to the Data Subject as merchant of record, and in"
    " doing so acts as a controller in its own right, under its own terms and privacy"
    " notice. It receives from the Controller the number of the Data Subject's account and"
    " a code derived from it, and nothing else. Paddle's checkout opens upon the Service's"
    " plans page, in a frame served by Paddle, by means of a script which that page alone"
    " loads from Paddle, and only after the Data Subject has pressed to pay. In opening it"
    " the Data Subject's browser connects to Paddle, which thereby receives the browser's"
    " network address and technical details of the device and browser, and may set cookies"
    " of its own, in accordance with its own privacy notice and cookie notice. What the"
    " Data Subject supplies upon that checkout, including their electronic mail address and"
    " card details, is supplied to Paddle and not to the Controller. Paddle issues the"
    " receipt or invoice for each sale and handles any refund.",
    "Save as provided at clauses 4.2 and 4.3, the Controller discloses personal data only",
    "Where the Data Subject pays for a plan or for further credits, the number of their"
    " account and a code derived from it are transmitted to Paddle.com Market Limited in"
    " the United Kingdom, a country in respect of which the European Commission has adopted"
    " a decision of adequacy; and the Data Subject's browser, in opening Paddle's checkout,"
    " connects to Paddle directly. No other transfer of personal data outside the European"
    " Economic Area is undertaken.",
    "On the plans page alone, and only once the Data Subject has pressed to pay, the page"
    " loads Paddle's checkout, which may set cookies of Paddle's own within its frame;"
    " these are Paddle's, governed by Paddle's cookie notice, and the Controller neither"
    " reads nor receives them.",
]

RETENTION = [
    "An account closed by the User. Seven days from the request for closure or, where a"
    " plan paid through Paddle is then current, upon the later day on which Paddle reports"
    " that plan cancelled. Closure of the account requests that cancellation, to take"
    " effect at the end of the period already paid for. Upon expiry the following are"
    " deleted: words, meanings, phrases, documents, dates of reading, records of use of the"
    ' reader, messages sent by means of "Tell us", fault reports bearing the account,'
    " sessions, authentication links, the plan, the periods for which it was paid and the"
    " records of purchases of further credits, and the account record itself, together"
    " with all files generated for the account.",
    "Records of payment. For so long as the account subsists, and deleted with it in"
    " accordance with clause 1.6 above. No invoice or receipt is retained by the"
    " Controller: Paddle.com Market Limited, as the seller, issues and retains them for such"
    " period as the law requires of it.",
    "Records of notifications from Paddle. Retained without limit of time. Each bears an"
    " identifier assigned by Paddle, its kind and the time of its receipt, and no account."
    " It is kept so that a notification sent twice is acted upon once.",
]


@pytest.mark.parametrize("words", PRIVACY)
def test_the_privacy_notice_says_davids_words(words: str) -> None:
    assert words in said(legal_page("privacy"))


@pytest.mark.parametrize("words", RETENTION)
def test_the_retention_schedule_says_davids_words(words: str) -> None:
    assert words in said(legal_page("retention"))


def test_paddle_is_its_own_recipient_clause_and_the_old_4_3_follows_it() -> None:
    page = said(legal_page("privacy"))
    recipients = page.split("Recipients", 1)[1].split("Transfers to third countries", 1)[0]
    assert recipients.index("Paddle.com Market Limited (United Kingdom)") < recipients.index(
        "Save as provided at clauses 4.2 and 4.3"
    )
    assert "Save as provided at clause 4.2," not in page
