"""Four pages, and what each one is for.

Learn is where you land and carry on. The Library is where you find something new. Words
is where you study. Add is where you bring a text targum does not have — which used to be
the front door, back when bringing your own was the only way to have anything at all.

The tests that matter most here are the ones about the *move*: a capability that existed
on one page and now exists on another is exactly the kind of thing that goes missing
quietly, and the file input is the one whose loss would mean no way to read your own book
except the command line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum.render.builder import add_page, learn_page, library_page, words_page

PAGES = {
    "learn": learn_page("k"),
    "library": library_page("k"),
    "words": words_page("k"),
    "add": add_page("k"),
}


# -- nothing was lost in the move ---------------------------------------------


def test_add_still_does_everything_only_it_could() -> None:
    """The regression that matters most.

    Every one of these existed on the start page and nowhere else in the product. Losing
    any of them to a page move would leave no way to read your own book except the
    command line, and nothing would fail loudly to say so.
    """
    add = PAGES["add"]
    assert 'type="file"' in add, "the file input"
    assert 'accept=".txt,.md,.markdown,.epub"' in add, "and what it accepts"
    assert 'id="drop"' in add, "the drop zone"
    assert 'id="source"' in add, "the free-text source field"
    assert 'id="from"' in add and 'id="to"' in add, "both language selects"
    assert 'value=""' in add, "including work-it-out-for-me"
    assert 'id="status"' in add, "the price-before-you-commit surface"


def test_only_add_builds_anything() -> None:
    """The front door stopped being a form, which is the whole point of the change."""
    for name in ("learn", "library", "words"):
        page = PAGES[name]
        assert 'type="file"' not in page, f"{name} should not take uploads"
        assert 'id="source"' not in page, f"{name} should not take a source"


def test_the_library_carries_nothing_personal() -> None:
    """It answers to a stranger and to a signed-in reader with the same thing now, which
    is what makes it coherent. Anything belonging to somebody lives on Learn."""
    library = PAGES["library"]
    assert 'id="catalogue"' in library, "the catalogue is the page"
    assert 'id="library-list"' not in library, "the shelf moved to Learn"
    assert 'id="trash-list"' not in library, "and so did the trash"
    assert 'href="/add"' in library, "but it says where to go when nothing fits"


def test_learn_carries_what_belongs_to_the_reader() -> None:
    learn = PAGES["learn"]
    assert 'id="carry"' in learn, "what you came back for"
    assert 'id="library-list"' in learn, "your shelf"
    assert 'id="trash-list"' in learn, "your trash"
    assert 'id="tiles"' in learn and 'id="growth"' in learn, "your numbers"
    assert 'id="catalogue"' not in learn, "the catalogue has its own page"


# -- the nav -------------------------------------------------------------------


def test_every_page_carries_the_same_four_places() -> None:
    """One nav file, because copies drift — they had drifted into three different orders
    once already."""
    for name, page in PAGES.items():
        found = re.findall(r'data-nav="(\w+)"', page)
        assert found == ["learn", "library", "words", "add"], name


def test_the_nav_marks_where_you_are() -> None:
    for name, page in PAGES.items():
        current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', page)
        assert current == [name], f"{name} should mark itself and nothing else"


def test_adding_is_last_because_it_is_rarest() -> None:
    """Nav order is how often somebody wants each one. Add used to be first."""
    order = re.findall(r'data-nav="(\w+)"', PAGES["learn"])
    assert order.index("add") == len(order) - 1
    assert order.index("learn") == 0


# -- what each page says it is --------------------------------------------------


def test_add_no_longer_introduces_the_product() -> None:
    """Positioning copy is for a front door. On a page reached from the nav by somebody
    who already has an account and a shelf, it is a stranger's greeting to a regular."""
    add = PAGES["add"]
    assert "Hebrew, with the translation beside it" not in add
    assert "Add a text" in add


def test_add_mentions_the_library_before_asking_anybody_to_pay() -> None:
    """Most of what anybody wants is already on a shelf, and finding that out after
    paying is the wrong way round."""
    add = PAGES["add"]
    said = add[add.index("Add a text") : add.index('id="drop"')]
    assert "Library" in said and 'href="/library"' in said


def test_learn_is_honest_when_there_is_nothing() -> None:
    """This is the onboarding now, so it points at the shelves rather than at a form."""
    learn = PAGES["learn"]
    empty = learn[learn.index('id="nothing"') :]
    assert "Nothing here yet" in empty
    assert 'href="/library"' in empty, "which is where to go"
    assert 'href="/add"' in empty, "with your own text as the quieter option"


# -- the charts are shared, not copied ------------------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"


def test_the_growth_chart_is_defined_once() -> None:
    """Two pages draw it. A second copy is a chart that drifts — the words page would
    keep a fix and Learn would not, and nobody would notice for months.
    """
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert "function drawGrowth(" in charts
    assert "function drawTiles(" in charts
    for page in ("words.js", "learn.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function drawGrowth(" not in source, f"{page} should use the shared one"


@pytest.mark.parametrize("page", ["words", "learn"])
def test_a_page_that_draws_charts_loads_them_first(page: str) -> None:
    """The first version of this said `"charts.js" in html or "TargumCharts" in html`,
    which passes on any page whose own script merely *mentions* the global — so Learn
    shipped without charts.js at all and the assertion stayed green. Look for the
    definition, not the name."""
    html = PAGES[page]
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    body = charts[charts.index("window.TargumCharts =") :][:80]
    assert body in html, f"{page} does not inline charts.js"
    own = (ASSETS / f"{page}.js").read_text(encoding="utf-8")[:200]
    assert html.index(body) < html.index(own), "and before the page that uses them"


# -- the upsell, and the two things it got wrong ---------------------------------


def test_open_it_opens_the_text() -> None:
    """It used to go to the library index — the page the text happens to sit on rather
    than the text it had just named. Every catalogue text has its own page now."""
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert 'keyed("/" + entry.shelf + "/" + entry.id)' in source


def test_translate_it_anyway_works_for_a_dropped_file() -> None:
    """It re-sent only `source`, so the override worked for a pasted link and silently
    did nothing for an upload — the one case somebody is most likely to insist on."""
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    retry = source[source.index("anyway.onclick") : source.index("row.appendChild(anyway)")]
    assert "readFile(chosen)" in retry, "a file has to be able to take this branch"
    assert ".catch(" in retry, "and a dropped connection must not leave the buttons dead"


# -- the library is a room, and says which one -----------------------------------


def test_the_library_heading_follows_the_shelf() -> None:
    """It is a page now rather than a panel, so the heading is the room. It read
    "Library" with the Beit Midrash open, which is the one thing a reader keeping Tanakh
    apart from secular material would notice first."""
    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert 'document.getElementById("page-title")' in source
    assert 'document.title = name + " — targum"' in source, "and the bookmark too"
    assert 'id="page-title"' in PAGES["library"], "the heading it writes into"


def test_the_library_has_one_heading() -> None:
    """ "Picked for you" was a panel title on a page that also held the reader's shelf
    and their trash. With nothing else on the page it only repeated the h1."""
    library = PAGES["library"]
    assert "Picked for you" not in library
    assert len(re.findall(r"<h2\b", library)) == 0


# -- the header every page wears --------------------------------------------------


def test_every_page_styles_its_own_header() -> None:
    """The add page loaded no file called "library", because it has no catalogue — and
    the header rules lived in library.css, so its brand mark rendered 675px across and
    its header a thousand tall. Nothing failed; it just looked broken.

    Anything belonging to `_nav.html.j2` belongs in chrome.css, which is why this asserts
    against the rules rather than against the filename.
    """
    for name, page in PAGES.items():
        for rule in (".site-head", ".brand-mark", ".site-nav", ".account-panel"):
            assert rule in page, f"{name} wears the header but does not style {rule}"


def test_the_chrome_is_not_in_the_library() -> None:
    """Where it was, and where it must not go back to."""
    library = (ASSETS / "library.css").read_text(encoding="utf-8")
    for rule in (".site-head {", ".brand-mark {", ".site-nav {", ".account-panel {"):
        assert rule not in library, f"{rule} belongs in chrome.css"


# -- every script parses ----------------------------------------------------------


def test_every_script_parses() -> None:
    """reader.js had this check; nothing else did.

    Splitting the charts out of words.js left its closing brace behind in one file and
    missing from the other. charts.js then failed to parse, `window.TargumCharts` was
    never assigned, and the words page threw on its first line and rendered a header
    over an empty screen. Every test passed: they all read the HTML as a string, and the
    broken script was inlined into it perfectly.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")

    broken = []
    for script in sorted(ASSETS.glob("*.js")):
        done = subprocess.run(
            [node, "--check", str(script)], capture_output=True, text=True, timeout=30
        )
        if done.returncode != 0:
            broken.append(f"{script.name}: {done.stderr.strip().splitlines()[-1]}")
    assert not broken, "\n".join(broken)
