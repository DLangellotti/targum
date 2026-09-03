"""The four pages targum owes a reader about their own data.

A7 on the roadmap, and the one item both planning documents call overdue rather than
pending: since Aug 27 accounts have held a real email address and word lists carrying
somebody's own writing, with nothing written down about any of it.

What a test can hold is that the pages exist, that they are reachable from the two places
a reader actually stands — the door and the foot — and that the numbers they state in
words are the numbers the code enforces. Whether the prose is any good is `test_brand.py`
and the guidelines behind it.
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from targum.accounts import GRACE_DAYS, LINK_MINUTES, SESSION_DAYS
from targum.backup import KEEP
from targum.render.builder import (
    LEGAL,
    about_page,
    holding_page,
    legal_is_public,
    legal_page,
    shelf_page,
    signin_page,
    you_page,
)
from targum.serve import LEGAL_ROUTES, OPEN_TO_STRANGERS, TRASH_DAYS

ADDRESS = "https://targum.page"


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documents as they will be at beta. Shut is the default everywhere else."""
    monkeypatch.setenv("TARGUM_PUBLIC_LEGAL", "1")


def said(markup: str) -> str:
    """The prose a reader actually meets, with the markup and the wrapping gone.

    Asserting against the file would be asserting against where the lines happen to
    break, which reflowing a paragraph would fail for no reason worth failing for.
    """
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def test_there_are_four_of_them() -> None:
    """A privacy statement, terms, a retention rule and a deletion path, which is the
    list the roadmap asks for by name."""
    assert set(LEGAL) == {"privacy", "terms", "retention", "deletion"}


@pytest.mark.parametrize("which", sorted(LEGAL))
def test_each_one_names_itself_and_says_who_to_write_to(which: str) -> None:
    """A canonical address so four pages do not compete with each other, and an address
    a person can write to — a deletion path with no way to ask is not a path."""
    html = legal_page(which, ADDRESS)
    assert f'href="{ADDRESS}/{which}"' in html
    assert "hello@targum.page" in html


def test_they_are_shut_by_default() -> None:
    """Shut for the alpha, the same way the catalogue is shut and by the same switch
    shape. Default rather than opt-out: an environment that forgets to set the variable
    gets the closed door, not the open one."""
    assert not legal_is_public()


def test_nothing_links_to_them_while_they_are_shut() -> None:
    """A link to a 404 is worse than no link, and a footer is the easiest place to leave
    one behind. Every surface that will carry them at beta is checked here for not
    carrying them now."""
    for page in (
        signin_page(),
        holding_page(),
        about_page(),
        shelf_page(ADDRESS),
        you_page("key"),
    ):
        for route in LEGAL_ROUTES:
            assert f'href="{route}"' not in page, route


def test_a_stranger_is_allowed_to_read_them_once_they_are_open(opened: None) -> None:
    """The failure the documents exist to prevent, and it fails quietly: a route missing
    from `OPEN_TO_STRANGERS` serves the holding page rather than an error, so a privacy
    notice nobody signed out can read looks exactly like one that works. Asserted now so
    that throwing the switch at beta is the only thing throwing the switch has to do.
    """
    assert LEGAL_ROUTES
    for route in LEGAL_ROUTES:
        assert route in OPEN_TO_STRANGERS, route


def test_the_door_and_the_foot_reach_them_once_they_are_open(opened: None) -> None:
    """Linked from the sign-in page and the foot, which is what the item asks for.

    The sign-in page most of all: it is the one screen where somebody hands over an
    email address, and it carried no footer at all before this.
    """
    for page in (signin_page(), holding_page(), about_page(), shelf_page(ADDRESS)):
        assert 'href="/privacy"' in page
        assert 'href="/terms"' in page


def test_the_erasure_procedure_sits_beside_the_button_it_describes(opened: None) -> None:
    """Privacy and terms are enough for a footer. The erasure procedure belongs next to
    Delete account, which is the only place anybody goes looking for it."""
    assert 'href="/deletion"' in you_page("key")


def test_the_seven_days_are_said_whether_or_not_the_link_is_there() -> None:
    """The link goes while the documents are shut; the fact does not. Somebody about to
    press Delete account still needs to know it waits a week."""
    assert "Deleting waits seven days" in you_page("key")


def test_privacy_hands_on_to_the_other_two() -> None:
    """Four documents, two links in the foot: the schedule and the procedure are one
    click on from the notice that incorporates them."""
    privacy = legal_page("privacy")
    assert 'href="/retention"' in privacy
    assert 'href="/deletion"' in privacy


def test_the_numbers_said_in_words_are_the_ones_the_code_enforces() -> None:
    """The retention rule is prose about constants, and prose drifts from constants.

    This is the guard, and it is deliberately blunt: change one of these and the test
    fails next to the page that would otherwise have gone on claiming the old number.
    """
    assert TRASH_DAYS == 7, "the trash page says seven days"
    assert GRACE_DAYS == 7, "the deletion page says seven days"
    assert LINK_MINUTES == 20, "the retention page says twenty minutes"
    assert SESSION_DAYS == 90, "the retention page says ninety days"
    assert KEEP == 14, "the retention page says the last fourteen backups"

    retention = said(legal_page("retention"))
    for stated in ("Twenty minutes", "Ninety days", "Seven days", "fourteen most recent"):
        assert stated in retention, stated
    assert "not less than seven days" in retention, "the sweep runs at start-up, and that is said"
    assert "within thirty days of receipt" in retention, "what the translator does on its own"


def test_the_privacy_page_carries_what_a_notice_has_to_carry() -> None:
    """GDPR Article 13 is a list, and a notice missing an item off it is not a notice.

    Checked here because the failure is silent: a privacy page that reads well and omits
    the legal basis or the right to complain looks exactly like one that does not. Each
    assertion below is an item of Article 13(1) or 13(2).
    """
    page = said(legal_page("privacy"))

    assert "David Langellotti" in page, "13(1)(a): identity of the controller"
    assert "hello@targum.page" in page, "13(1)(a): contact details of the controller"
    assert "not appointed a data protection officer" in page, "13(1)(b): the DPO, or its absence"
    assert "Article 6(1)(b)" in page, "13(1)(c): the legal basis for the account"
    assert "Article 6(1)(f)" in page, "13(1)(d): processing on legitimate interests"
    assert "legitimate interests of the Controller" in page, "13(1)(d): the interests, named"
    for recipient in ("Hetzner", "Resend", "Anthropic"):
        assert recipient in page, f"13(1)(e): {recipient} is a recipient and is named"
    assert "third country" in page, "13(1)(f): the transfer is identified as one"
    assert "Data Retention Schedule" in page, "13(2)(a): the periods, incorporated by reference"
    assert "Article 77" in page, "13(2)(d): the right to lodge a complaint"
    assert "supervisory authority" in page, "13(2)(d): with whom"
    assert "unable to furnish an account in its absence" in page, "13(2)(e): the consequence"
    assert "Article 22" in page, "13(2)(f): automated decision-making"
    for article in ("Article 15", "Article 16", "Article 17", "Article 18", "Article 20"):
        assert article in page, f"13(2)(b): the right under {article}"


#: The four documents by the name each is cited under, so that a cross-reference like
#: "clause 6.1 of the Terms of Service" resolves against the document it points into.
BY_NAME = {
    "Privacy Notice": "privacy",
    "Terms of Service": "terms",
    "Data Retention Schedule": "retention",
    "Erasure and Account Closure Procedure": "deletion",
}

#: A citation: a clause number, and optionally the document it belongs to. The document
#: names are matched by alternation rather than by a lazy character class, which stops
#: at the first space and turns "Privacy Notice" into "Privacy".
CITATION = re.compile(r"clause (\d+)\.(\d+)(?:\s+of the\s+(" + "|".join(BY_NAME) + r"))?")


def clauses_per_section(html: str) -> dict[int, int]:
    """How many clauses each numbered section holds, counted as the page counts them.

    The numbers are drawn by CSS counters, so no "7.4" appears in the markup and none
    can be searched for. Sections count off `<h2>` and clauses off the `<li>` of each
    `ol.clauses`, which is what the stylesheet does.
    """
    found: dict[int, int] = {}
    section = 0
    for chunk in re.split(r"(?=<h2>)", html):
        if not chunk.startswith("<h2>"):
            continue
        section += 1
        lists = re.findall(r'<ol class="clauses">(.*?)</ol>', chunk, re.S)
        found[section] = sum(len(re.findall(r"<li>", one)) for one in lists)
    return found


def test_every_cross_reference_points_at_a_clause_that_exists() -> None:
    """A numbered instrument that cites itself is only as good as its numbering.

    Formal drafting buys the reader a clause to cite. It also buys four documents that
    cite each other by number, and a reference to clause 1.5 of a schedule whose first
    section is an unnumbered list is worse than no reference at all. Inserting one
    clause renumbers every clause after it, which is exactly when this fails.
    """
    pages = {which: legal_page(which) for which in LEGAL}
    counts = {which: clauses_per_section(html) for which, html in pages.items()}

    seen = 0
    for which, html in pages.items():
        for section, clause, named in CITATION.findall(said(html)):
            target = BY_NAME.get(named, which)
            held = counts[target].get(int(section), 0)
            assert 1 <= int(clause) <= held, (
                f"{which} cites clause {section}.{clause} of the {target} document, "
                f"whose section {section} holds {held} clauses"
            )
            seen += 1
    assert seen >= 6, f"only {seen} citations found; the pattern has stopped matching"


def test_the_credit_the_licence_asks_for_is_on_every_page() -> None:
    """The structure and much of the phrasing is adapted from 37signals' policies, which
    are CC BY 4.0. Attribution is the one condition that licence has, so it is worth a
    test rather than a good intention."""
    for which in LEGAL:
        page = said(legal_page(which))
        assert "37signals" in page and "CC BY 4.0" in page, which


def test_the_terms_take_a_position_on_what_a_reader_uploads() -> None:
    """The roadmap names this exactly: private per person, never shared, a takedown
    path. It is the half of A7 that is about somebody else's copyright as well as
    their privacy."""
    terms = said(legal_page("terms"))
    assert "David Langellotti" in terms, "somebody is on the other side of these terms"
    assert "Affero General Public License" in terms, "the pipeline's licence"
    assert "retains all right, title and interest in User Content" in terms
    assert "entitled to supply User Content" in terms, "the warranty the User gives"
    assert "stored under the User's account alone" in terms, "private per person, and said so"
    assert "shall remove the material complained of" in terms, "the takedown obligation"
    assert "Notice of infringement" in terms, "and it has a clause of its own"


def test_the_name_is_reserved_where_the_licence_is_not() -> None:
    """The AGPL is a licence on the code and says nothing about the name. `NOTICE` says
    it: a derived product or service is not called targum, and `LICENSING.md` sends a
    reader there so the reservation is found beside the grant it qualifies."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    assert "targum" in notice and "name" in notice
    assert "grants no right" in notice
    assert "derived product or service" in notice
    assert "`NOTICE`" in (root / "LICENSING.md").read_text(encoding="utf-8")
    assert '"NOTICE"' in (root / "pyproject.toml").read_text(encoding="utf-8")
