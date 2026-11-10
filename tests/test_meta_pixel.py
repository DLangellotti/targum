"""The Meta pixel: one page, after a yes, and nowhere else (design.md §12, 2026-11-10).

targum-internal#676 tests whether people who have finished Duolingo Hebrew are targum's
first readers, with a Meta ad landing on a page written for them. The page may carry
Meta's pixel. Every other page, and every reader above all, still fetches nothing from
any other site.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from targum.render.builder import LEGAL_CHANGED, legal_page

SRC = Path(__file__).resolve().parents[1] / "src" / "targum"

#: Meta's hosts and the name of its pixel script. Anything in the source that names one
#: of these is loading, or linking to, Meta's code.
META = re.compile(r"connect\.facebook\.net|facebook\.com/tr|fbevents|fbq\(")

#: The one file that may name them: the /after-duolingo page. A second needs a §12 entry.
ALLOWED = frozenset({"render/templates/after_duolingo.html.j2", "render/assets/after-duolingo.js"})


def _said(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html)))


def test_only_the_after_duolingo_page_names_meta() -> None:
    naming = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".j2", ".html", ".js", ".css", ".json"}
        and META.search(path.read_text(errors="ignore"))
    )
    assert set(naming) <= ALLOWED, naming


def test_the_notice_says_the_measurement_word_for_word() -> None:
    """David approved the wording on 2026-11-10 (targum-internal#676)."""
    assert LEGAL_CHANGED == "10 November 2026"
    page = _said(legal_page("privacy"))
    assert (
        "No processing is undertaken for the purposes of advertising, save the measurement"
        " described at clause 3.15 on the one page named there" in page
    )
    assert (
        "The Service transmits no data to any provider of analytics and employs no"
        " third-party script, save on that page and only with the consent described at"
        " clause 3.15" in page
    )
    assert (
        "On the page of the Service at /after-duolingo only, and only where the visitor has"
        " first agreed on that page, a script of Meta Platforms Ireland Limited records the"
        " visit" in page
    )
    assert "Until the visitor agrees, the page loads nothing from Meta" in page
    assert "Legal basis: Article 6(1)(a), the consent of the visitor" in page
    assert "as joint controller with the Controller and not as its processor" in page
    assert "EU–US Data Privacy Framework" in page


def test_the_schedule_says_where_the_choice_is_kept() -> None:
    page = _said(legal_page("retention"))
    assert "Kept in the visitor's own browser for one year, and not by the Controller." in page
