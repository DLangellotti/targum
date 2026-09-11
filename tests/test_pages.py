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

import html
import re
from pathlib import Path

import pytest

from targum.render.builder import (
    add_page,
    chat_page,
    learn_page,
    library_page,
    list_page,
    progress_page,
    you_page,
)

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "templates"

PAGES = {
    "learn": learn_page("k"),
    "you": you_page("k"),
    "library": library_page("k"),
    "progress": progress_page("k"),
    "texts": list_page("k", "texts"),
    "words": list_page("k", "words"),
    "phrases": list_page("k", "phrases"),
    "add": add_page("k"),
    "chat": chat_page("k"),
}
#: The conversation page framed in the front page (2026-09-11): not a place of its own,
#: so not in the table every-page tests walk — it has no bar to walk.
EMBED = chat_page("k", embed=True)


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
    assert 'id="status"' in add, "the price-before-you-commit surface"


def test_the_library_and_the_progress_page_build_nothing() -> None:
    """The front door stopped being a form, which was the whole point of the change;
    since 2026-09-06 it carries one press instead, the `+` on the box, which prices a
    file in place and is not a form either. The library and the progress page take
    nothing at all."""
    for name in ("library", "progress"):
        page = PAGES[name]
        assert 'type="file"' not in page, f"{name} should not take uploads"
        assert 'id="source"' not in page, f"{name} should not take a source"
    learn = PAGES["learn"]
    assert 'id="source"' not in learn and 'id="drop"' not in learn, "no form on the front door"
    assert learn.count('type="file"') == 0, "the + is in the framed conversation (2026-09-11)"
    assert EMBED.count('type="file"') == 1, "one hidden input behind the +"


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
    assert 'id="known-line"' in learn, "how much of the language you have"
    assert 'id="carry"' in learn, "what you came back for"
    assert 'id="library-list"' in learn, "your shelf"
    assert 'id="trash-list"' in learn, "your trash"
    assert 'id="word-table"' in learn and 'id="phrase-list"' in learn, "what you know"
    assert 'id="catalogue"' not in learn, "the catalogue has its own page"


def test_learn_says_what_to_do_next() -> None:
    """Carry on, or: find something, bring something, see what you have built. The card
    comes first because most visits are somebody returning to a text."""
    learn = PAGES["learn"]
    steps = re.findall(r'data-door="(\w+)"', learn)
    assert steps == ["library", "progress"], "bringing a text is the `+` on the box"
    assert 'id="carry"' in learn[: learn.index('data-door="library"')], "the card comes first"
    assert 'id="suggest"' in learn, "and something to read, picked for this reader"


def test_the_numbers_belong_to_the_progress_page() -> None:
    """Learn used to carry a smaller, worse copy of both charts. One place counts, and it
    is the page somebody goes to on purpose."""
    learn, progress = PAGES["learn"], PAGES["progress"]
    assert 'id="tiles"' not in learn and 'id="growth"' not in learn
    assert 'id="growth"' in progress


def test_the_progress_page_is_only_the_numbers() -> None:
    """No table, no list, no export. Everything a reader works on moved to Learn, and a
    page that is half metrics and half working surface is neither."""
    progress = PAGES["progress"]
    for gone in ('id="word-table"', 'id="phrase-list"', 'id="search"', 'id="export-all"'):
        assert gone not in progress, f"{gone} belongs to Learn now"
    assert 'id="ledger"' in progress and 'id="milestones"' in progress


# -- the nav -------------------------------------------------------------------


def test_every_page_carries_the_same_three_places() -> None:
    """One nav file, because copies drift — they had drifted into three different orders
    once already. Three since 2026-09-06: the chat, second here for a day, is the box at
    the top of Learn, and uploading, which was a corner, is the `+` on that box."""
    for name, page in PAGES.items():
        found = re.findall(r'data-nav="(\w+)"', page)
        assert found == ["learn", "library", "progress"], name


#: Reached from somewhere other than the nav — a profile is not one of the places you
#: can be, it is who you are while you are in one of them; and bringing a text is the
#: `+` on the box, a thing you do while asking.
NOT_IN_THE_NAV = {"you", "add"}

#: Learn's lists, gone to a page of their own, and the conversation, which is where a
#: line typed into Learn's box goes. They mark Learn, which is where they came from and
#: the only nav entry that could honestly be current.
UNDER_LEARN = {"texts", "words", "phrases", "chat"}


def test_the_nav_marks_where_you_are() -> None:
    for name, page in PAGES.items():
        current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', page)
        if name in NOT_IN_THE_NAV:
            assert current == [], f"{name} is not a nav destination and marks nothing"
            continue
        if name in UNDER_LEARN:
            assert current == ["learn"], f"{name} is one of Learn's lists"
            continue
        assert current == [name], f"{name} should mark itself and nothing else"


def test_bringing_a_text_is_the_box_and_not_a_place() -> None:
    """Add used to be first in the nav, then the corner. Since 2026-09-06 it is the `+`
    on the box, on both pages that carry one, and nothing in the nav points at it."""
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert 'id="chat-bring"' in page and 'id="chat-file"' in page, name
        assert 'class="upload' not in page, name
    assert 'id="talk-frame"' in PAGES["learn"], "Learn frames the page that carries it"
    bring = (ASSETS / "bring.js").read_text(encoding="utf-8")
    assert 'keyed("/add")' in bring, "the Add page is one link away, on the card"
    order = re.findall(r'data-nav="(\w+)"', PAGES["learn"])
    assert order.index("learn") == 0


def test_the_front_page_opens_on_the_sheet_beside_the_conversation() -> None:
    """design.md §13 (2026-09-11): the text to read, drawn as a page on the desk with its
    first lines, and the conversation beside it; the chrome's face carried in every page
    that wears the bar; the reader never loads it."""
    learn = PAGES["learn"]
    assert (
        learn.index('class="front"')
        < learn.index('id="carry-sheet"')
        < learn.index('id="talk-title"')
    )
    assert 'id="carry-frame"' in learn and 'class="open" id="carry"' in learn
    assert 'id="carry-expand"' in learn and 'id="talk-hide"' in learn and 'id="talk-cta"' in learn
    for name, page in list(PAGES.items()) + [("embed", EMBED)]:
        assert page.count('font-family:"Source Sans 3"') == 2, (
            f"{name}: the chrome face, upright and italic"
        )
    from targum.render.builder import ASSETS

    reader = (ASSETS / "reader.css").read_text(encoding="utf-8")
    assert "--chrome:" in reader and "--ground:" in reader and "--teal:" in reader


def test_the_front_page_names_its_parts_and_frames_the_conversation() -> None:
    """2026-09-11: "nothing is labeled", "I can't really tell that it's a chat", "I should
    not be sent to a new page", then "an actual embed of the chat". The conversation is
    a named section with a sentence under its heading, and in it the conversation page
    itself, framed without its bar; what follows is a named section too. The framed
    page opens every link in the page that holds it."""
    learn = PAGES["learn"]
    assert "Talk to targum" in learn and 'id="talk-frame"' in learn
    assert 'src="/chat?embed=1&amp;k=k"' in learn
    assert 'id="composer"' not in learn and "TargumChat" not in learn, "the box is in the frame"
    assert 'class="section-title" id="read-title">Read<' in learn
    assert (
        learn.index('id="talk-title"')
        < learn.index('id="talk-frame"')
        < learn.index('id="read-title"')
    )
    assert 'class="chat embed"' in EMBED and '<base target="_top">' in EMBED
    assert 'class="site-head"' not in EMBED and "data-nav=" not in EMBED, "no bar, no foot"
    assert 'id="composer"' in EMBED and 'id="chat-thread"' in EMBED and "TargumChat" in EMBED
    assert 'class="chat"' in PAGES["chat"] and "<base " not in PAGES["chat"]


def test_the_box_is_the_front_door() -> None:
    """Learn carries the box under the ledger's own sentence, and the conversation page
    carries the same one from the same file: one field, the `+`, Speak, Send."""
    learn = PAGES["learn"]
    assert (
        learn.index('id="known-line"')
        < learn.index('id="carry-sheet"')
        < learn.index('id="talk-frame"')
    ), "under the count, beside the sheet (§13)"
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        for control in ('id="chat-bring"', 'id="chat-mic"', 'id="chat-send"', 'id="chat-said"'):
            assert page.count(control) == 1, f"{name}: {control} once"


def test_the_box_s_actions_are_glyphs_with_the_word_as_their_label() -> None:
    """Since 2026-09-10 (targum-internal#235) Speak, Send and Hear are drawn, not written:
    a microphone, an arrow, a loudspeaker from one sprite, each to §7 — sixteen pixels,
    no fill, a stroke at 1.4 with round caps — and the word kept as the label, so a
    screen reader says what the button used to say. The `+` stays typed, as §7 keeps
    typed characters as themselves."""
    sprite = (TEMPLATES / "_glyphs.html.j2").read_text(encoding="utf-8")
    symbols = re.findall(r'<symbol id="glyph-(\w+)" viewBox="([^"]+)">', sprite)
    assert sorted(name for name, _ in symbols) == ["hear", "mic", "send", "stop"]
    assert all(box == "0 0 16 16" for _, box in symbols), "§7: a 16px viewBox"
    assert 'fill="' not in sprite and "stroke=" not in sprite, "the stroke is the stylesheet's"
    glyph = (ASSETS / "composer.css").read_text(encoding="utf-8")
    rule = glyph[glyph.index(".glyph {") : glyph.index("}", glyph.index(".glyph {"))]
    for line in (
        "fill: none",
        "stroke: currentColor",
        "stroke-width: 1.4",
        "stroke-linecap: round",
    ):
        assert line in rule, f"§7: {line}"
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert page.count('<svg class="glyphs"') == 1, f"{name}: the sprite, once"
        for control, word, glyph_name in (
            ("chat-mic", "Speak", "mic"),
            ("chat-send", "Send", "send"),
        ):
            button = re.search(rf'<button[^>]*id="{control}"[^>]*>(.*?)</button>', page, re.S)
            assert button, control
            tag = page[page.rfind("<button", 0, button.start(1)) : button.start(1)]
            assert f'aria-label="{word}"' in tag and f'title="{word}"' in tag, control
            assert f'href="#glyph-{glyph_name}"' in button.group(1), control
            assert not re.sub(r"<[^>]+>", "", button.group(1)).strip(), f"{control}: no words"
        plus = re.search(r'<button[^>]*id="chat-bring"[^>]*>(.*?)</button>', page, re.S)
        assert plus and plus.group(1).strip() == "+", "the + is typed (§7)"
    chat = (ASSETS / "chat.js").read_text(encoding="utf-8")
    assert 'button.setAttribute("aria-label", "Hear")' in chat and 'glyph("hear")' in chat
    speak = (ASSETS / "speak.js").read_text(encoding="utf-8")
    assert "textContent" not in speak, "Speak and Stop are labels now, not faces"


def test_the_hours_are_where_a_reader_looks_for_them_and_not_in_their_face() -> None:
    """Until 2026-09-10 the month's hours stood in the conversation page's side column on
    every visit. Now the count is under the ledger on Your Progress and in the account
    panel on every page, and the box says it only when the hours are nearly gone
    (targum-internal#237)."""
    for name, page in PAGES.items():
        assert page.count('id="account-hours"') == 1, f"{name}: the panel, once"
    assert PAGES["progress"].count('id="hours-line"') == 1
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert page.count('id="chat-hours"') == 1, f"{name}: one line, above the box"
        assert page.index('id="chat-hours"') < page.index('id="composer"'), name
    chat = PAGES["chat"]
    aside = chat[chat.index('class="chat-side"') : chat.index("</aside>")]
    assert "chat-hours" not in aside, "not in the side column any more"


def test_the_chips_stand_on_both_pages_that_carry_the_box() -> None:
    """targum-internal#240: under the box on Learn, in the empty state on the
    conversation page, drawn by one script both pages carry."""
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert page.count('id="chat-chips"') == 1, name
        assert "TargumChips" in page, f"{name}: chips.js rides"
        assert (
            page.index('id="chat-empty"') < page.index('id="chat-chips"') < page.index('id="turns"')
        )


def test_the_first_visit_s_question_stands_on_both_pages_with_the_languages_it_may_ask() -> None:
    """targum-internal#243."""
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert page.count('id="chat-first-lang"') == 1, name
        assert "TargumFirst" in page, f"{name}: first.js rides"
        assert 'window.TARGUM_INTO = ["en", "ru"]' in page, name


def test_words_you_may_already_know_stand_on_learn() -> None:
    """targum-internal#245: the way to say your level is higher than your count is to
    raise the count for real, a page of the commonest words at a time."""
    learn = PAGES["learn"]
    assert learn.count('id="claim-panel"') == 1 and 'id="claim-yes"' in learn
    assert 'id="claim-all"' in learn and 'aria-label="Check all"' in learn, (
        "a checkbox at the head checks the page (2026-09-11)"
    )
    assert "Words you may already know" in learn and "TargumClaim" in learn
    assert (
        learn.index('id="word-table"')
        < learn.index('id="claim-panel"')
        < learn.index('id="phrase-list"')
    ), "under Your Words, above Your Phrases"


# -- what each page says it is --------------------------------------------------


def test_add_no_longer_introduces_the_product() -> None:
    """Positioning copy is for a front door. On a page reached from the nav by somebody
    who already has an account and a shelf, it is a stranger's greeting to a regular."""
    add = PAGES["add"]
    assert "Hebrew, with the translation beside it" not in add
    # "Add", since a recording is as welcome as a text: the page's one word is the act.
    assert '<h1 class="lede">Add</h1>' in add


def test_add_points_at_the_library_before_asking_anybody_to_pay() -> None:
    """Most of what anybody wants is already there, and finding that out after paying is
    the wrong way round. The page had four names for one place — nav "Discover", tab
    "Library", card "Explore the Library", route /library — so it is Library everywhere
    now, and the route it always was."""
    add = PAGES["add"]
    said = add[add.index('<h1 class="lede">Add</h1>') : add.index('id="drop"')]
    assert "Library" in said and 'href="/library"' in said


def test_learn_is_honest_when_there_is_nothing() -> None:
    """Signed out, or the server gone, the page says so and points at the shelves."""
    learn = PAGES["learn"]
    empty = learn[learn.index('id="nothing"') :]
    assert "Nothing here yet" in empty
    assert 'href="/library"' in empty, "which is where to go"
    assert 'href="/add"' in empty, "with your own text as the quieter option"


def test_an_empty_shelf_still_gets_the_suggestion() -> None:
    """The suggestion — the one thing on Learn that says where to start — lives inside
    `#page`, and an empty shelf used to hide `#page` wholesale. So the reader with nothing
    was the one reader who never saw it, and the first alpha reader's first words were
    "no idea where to start"."""
    from targum.render.builder import ASSETS

    learn = PAGES["learn"]
    assert learn.index('id="page"') < learn.index('id="suggest"') < learn.index('id="nothing"')
    script = (ASSETS / "learn.js").read_text(encoding="utf-8")
    assert 'getElementById("page").hidden = nothing' not in script
    assert 'getElementById("page").hidden = false' in script


# -- the charts are shared, not copied ------------------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"


def test_the_growth_chart_is_defined_once() -> None:
    """Two pages draw it. A second copy is a chart that drifts — the words page would
    keep a fix and Learn would not, and nobody would notice for months.
    """
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert "function drawGrowth(" in charts
    for page in ("progress.js", "learn.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function drawGrowth(" not in source, f"{page} should use the shared one"


def baked(name: str) -> str:
    """A script as the page actually carries it, not as the file reads.

    Every asset is inlined with its comments taken out, and these files open with one —
    so a fingerprint cut from the raw source finds nothing in the page, and a test that
    cuts one is testing the stripper rather than the ordering it means to check.
    """
    from targum.render.builder import _strip

    return _strip(name, (ASSETS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("page", ["progress", "learn"])
def test_a_page_that_draws_charts_loads_them_first(page: str) -> None:
    """The first version of this said `"charts.js" in html or "TargumCharts" in html`,
    which passes on any page whose own script merely *mentions* the global — so Learn
    shipped without charts.js at all and the assertion stayed green. Look for the
    definition, not the name."""
    html = PAGES[page]
    charts = baked("charts.js")
    body = charts[charts.index("window.TargumCharts =") :][:80]
    assert body in html, f"{page} does not inline charts.js"
    own = baked(f"{page}.js")[:200]
    assert html.index(body) < html.index(own), "and before the page that uses them"


# -- the upsell, and the two things it got wrong ---------------------------------


def test_open_it_opens_the_text() -> None:
    """It used to go to the library index — the page the text happens to sit on rather
    than the text it had just named. Every catalogue text has its own page now."""
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert 'keyed("/library/" + entry.id)' in source


def test_translate_it_anyway_works_for_a_dropped_file() -> None:
    """It re-sent only `source`, so the override worked for a pasted link and silently
    did nothing for an upload — the one case somebody is most likely to insist on."""
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    retry = source[source.index("anyway.onclick") : source.index("row.appendChild(anyway)")]
    assert "readFile(chosen[0])" in retry, "a file has to be able to take this branch"
    assert "bringing.upload(chosen" in retry, "and so has a picture or a recording"
    assert ".catch(" in retry, "and a dropped connection must not leave the buttons dead"


# -- one catalogue, and what each text is ----------------------------------------


def test_the_library_is_one_list() -> None:
    """There were two shelves with a tab switcher between them. A reader had to know
    which room a text was in before they could find it, which is backwards for the one
    page whose whole job is finding something."""
    library = PAGES["library"]
    assert 'id="shelves"' not in library, "no room switcher"
    assert "Beit Midrash" not in library
    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert "SHELVES" not in source and "drawShelves" not in source


def test_a_row_says_what_the_text_is() -> None:
    """The visible half of the classification. With Tanakh, a novel and this morning's
    news in one list, the reader who cares which is which needs the row to say so — and
    it has to be the same vocabulary the catalogue is written in, so the two cannot
    drift."""
    from targum.catalogue import Kind, Register

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    for kind in Kind:
        assert f'["{kind.value}", ' in source, f"the library cannot name a {kind.value}"
    for register in Register:
        if register.value:
            assert f'["{register.value}", ' in source
    # And filters by both, which is the point of naming them. `state` is whichever set of
    # filters is being asked about — the live ones, or the same minus one, which is how
    # the page works out which chips are worth offering.
    assert "state.kind && row.kind !== state.kind" in source
    assert "state.register && row.register !== state.register" in source


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

    Splitting the charts out of progress.js left its closing brace behind in one file and
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


def test_the_collector_reads_all_three_stores() -> None:
    """The one function both pages depend on, run rather than grepped.

    Everything else here reads the built HTML as a string, which is how a charts.js that
    did not parse at all shipped green. This loads it the way a browser does — with a
    stub localStorage holding one word, one phrase and the document index that says
    which language the phrase belongs to — and checks what comes back.
    """
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")

    store = {
        "targum:docs": json.dumps({"h1": {"title": "judenstaat", "language": "he"}}),
        "targum:vocab:he": json.dumps(
            {
                "מילה": {"status": 9, "surface": "מילה", "band": "easy", "at": 100},
                "ספר": {"status": 2, "surface": "ספר", "band": "hard", "at": 200},
            }
        ),
        "targum:picked:h1": json.dumps({"s1": [{"text": "בית ספר", "status": 9, "at": 300}]}),
    }
    harness = """
const fs = require('fs');
const store = JSON.parse(process.argv[2]);
const keys = Object.keys(store);
const localStorage = {
  length: keys.length,
  key: i => keys[i],
  getItem: k => (k in store ? store[k] : null),
};
const make = () => ({ style: {}, dataset: {}, children: [],
  classList: { add() {}, remove() {} }, appendChild(c) { this.children.push(c); return c },
  setAttribute() {}, addEventListener() {},
  getBoundingClientRect: () => ({ width: 600, height: 200 }) });
const document = { createElement: make, createElementNS: make, getElementById: make,
                   querySelector: () => null, querySelectorAll: () => [], addEventListener() {} };
const window = { localStorage, document };
new Function('window', 'document', 'localStorage',
             fs.readFileSync(process.argv[1], 'utf8'))(window, document, localStorage);
if (!window.TargumCharts) throw new Error('TargumCharts was never assigned');
const he = window.TargumCharts.collect().he;
console.log(JSON.stringify({
  words: he.words.map(w => [w.lemma, w.status, w.at]),
  phrases: he.phrases.map(p => [p.term, p.title]),
}));
"""
    done = subprocess.run(
        [node, "-e", harness, "--", str(ASSETS / "charts.js"), json.dumps(store)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)

    # Words come from targum:vocab:<language>, oldest first, keeping their status.
    assert got["words"] == [["מילה", 9, 100], ["ספר", 2, 200]]
    # A phrase lives under its text, not its language, so the document index is what
    # says it is Hebrew — and what gives it a title to show.
    assert got["phrases"] == [["בית ספר", "judenstaat"]]


@pytest.mark.parametrize("page", ["progress", "learn"])
def test_the_chart_kit_is_bound_before_it_is_used(page: str) -> None:
    """`var` hoists the name and not the value.

    progress.js read `charts.collect` during start-up but declared `var charts` a hundred
    lines further down, beside the drawing code. The name existed, held `undefined`, and
    the page threw on load — with charts.js present, correct, and loaded first, which is
    what made it look like a loading-order problem it was not.
    """
    source = (ASSETS / f"{page}.js").read_text(encoding="utf-8")
    bound = source.index("var charts = window.TargumCharts;")
    # `charts.js` is the filename, and both files name it in a comment above the bind.
    first = re.search(r"\bcharts\.(?!js\b)\w+", source)
    assert first is not None, f"{page}.js no longer uses the shared kit"
    assert bound < first.start(), f"{page}.js reads {first.group(0)} before binding charts"


def test_the_library_is_a_list_you_can_sift() -> None:
    """Cards were the wrong shape once there was more than a screenful: a card cannot be
    sorted, and twenty-six of them are a wall."""
    library = PAGES["library"]
    for control in ("find", "register-chips", "kind-chips", "length", "difficulty"):
        assert f'id="{control}"' in library, f"the library cannot filter by {control}"
    assert 'id="rows-head"' in library, "and the columns sort"
    assert 'class="cards"' not in library, "the card grid is gone"


def test_the_catalogue_and_your_uploads_are_tabs_rather_than_a_filter() -> None:
    """What is there to read and what have I put here are two questions, not one setting.
    As a select called "Access" the second list was a thing nobody found."""
    library = PAGES["library"]
    assert 'id="where"' in library and 'role="tablist"' in library
    assert 'id="access"' not in library, "and the filter it replaces is gone"

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert '["library", "Library"]' in source and '["mine", "Your Uploads"]' in source
    # The cell is still there — a build narrates itself in it — but it no longer carries
    # a Public/Private word, because the tab above the list says that once.
    assert '"row-state", row.entry ? "Public" : "Private"' not in source


def test_a_row_carries_a_cover_and_falls_back_to_the_text() -> None:
    """The covers are drawn one at a time and arrive over months. A library with none of
    them yet has to look deliberate rather than broken."""
    library = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert 'keyed("/thumb/"' in library, "it asks for a cover"

    covers = (ASSETS / "covers.js").read_text(encoding="utf-8")
    assert "glyph.textContent = letter" in covers, "and draws the first letter meanwhile"
    swap = covers[covers.index("image.onload") : covers.index("image.src")]
    assert "box.textContent" in swap, "the letter is replaced only once the image loaded"


def test_the_cover_tile_is_defined_once() -> None:
    """Two pages draw one — the library's rows and Learn's chapters. A second copy is a
    tile that drifts: one page would keep a fix and the other would not."""
    covers = (ASSETS / "covers.js").read_text(encoding="utf-8")
    assert "function tile(" in covers
    for page in ("library.js", "learn.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function thumb(" not in source, f"{page} should use the shared tile"
        assert "TargumCovers.tile(" in source, f"{page} does not draw one"


@pytest.mark.parametrize("page", ["library", "learn"])
def test_a_page_that_draws_covers_loads_them_first(page: str) -> None:
    html = PAGES[page]
    covers = baked("covers.js")
    body = covers[covers.index("function tile(") :][:60]
    assert body in html, f"{page} does not inline covers.js"
    own = baked(f"{page}.js")[:200]
    assert html.index(body) < html.index(own), "and before the page that uses it"


def test_a_chapter_asks_for_its_own_cover_and_settles_for_its_book() -> None:
    """Most chapters in this library are numbered rather than titled — a hundred and
    fifty psalms — and a number is not a subject anything could draw. Only chapters that
    name something get their own; the rest fall back on the server."""
    covers = (ASSETS / "covers.js").read_text(encoding="utf-8")
    assert 'return book + "-c" + padded' in covers
    # The chapter tree moved out of learn.js when Learn stopped being the only page with
    # a shelf on it. Both pages draw it from here, which is the point of the move.
    shelf = (ASSETS / "shelf.js").read_text(encoding="utf-8")
    assert "TargumCovers.chapterName(" in shelf


def test_the_shelf_grid_outranks_the_list_it_shares_a_class_with() -> None:
    """A cascade trap, and the reason the columns did not line up.

    The shelf and the trash are both `ul.books`, and `.books li` sets `display: flex`
    further down the same file. At equal specificity the later rule wins, so every cell
    became a flex item packed to content width while the header above them stayed on the
    grid. Two classes beat one whatever the order, which is worth more here than
    depending on where a rule happens to sit.
    """
    css = (ASSETS / "library.css").read_text(encoding="utf-8")
    assert ".books.shelf-rows li {" in css, "the row grid has to out-specify .books li"
    assert not re.search(r"^\.shelf-rows li[ ,{]", css, re.M), "one class is not enough"
    # And the thing it has to beat is still there, below it.
    assert css.index(".books.shelf-rows li {") < css.index(".books li { display: flex")


# -- the profile page ------------------------------------------------------------


def test_the_profile_page_holds_what_an_account_is() -> None:
    """An account used to be an address, a session and a shelf. This is the page that
    says who you are, how you read, and how to end it."""
    you = PAGES["you"]
    assert 'id="you-name"' in you, "what to call you"
    assert 'id="you-email"' in you and 'id="you-avatar"' in you
    assert 'id="you-export"' in you and 'id="you-forget"' in you, "and the way out"


def test_the_profile_page_says_something_to_a_stranger() -> None:
    """Signed out there is nothing to show, and an empty form is not an answer."""
    you = PAGES["you"]
    assert 'id="stranger"' in you
    assert "Sign in from the corner" in you


def test_the_corner_is_a_circle_rather_than_an_address() -> None:
    """An address is too long for a corner and is nobody else's business on a shared
    screen. Initials fit, and a picture will drop into the same circle when a sign-in
    provider hands one over."""
    source = (ASSETS / "account.js").read_text(encoding="utf-8")
    assert 'open.className = "avatar"' in source
    assert "who.initials" in source
    assert "who.email.split" not in source, "the address stopped being the label"


# -- the three lists, and where the rest of each one lives ------------------------


def test_learn_caps_every_list_and_says_where_the_rest_is() -> None:
    """A page somebody lands on with four hundred rows on it is not a landing page."""
    learn = PAGES["learn"]
    for link, where in (
        ("shelf-more", "/texts"),
        ("words-more", "/words"),
        ("phrases-more", "/phrases"),
    ):
        assert f'id="{link}"' in learn, link
        assert f'href="{where}"' in learn, where


def test_every_list_on_learn_can_be_folded_away() -> None:
    learn = PAGES["learn"]
    assert learn.count('class="fold"') == 3, "the shelf, the words and the phrases"
    assert learn.count('class="fold-body"') == 3, "and each one folds a body"


def test_the_word_targum_is_defined_where_somebody_meets_it() -> None:
    """The product calls a built text a targum everywhere and had never once said what
    one is. Not "a text you have built", either: the glosses are cached per lemma across
    every text and every reader, and a public text is built once for everybody, so most
    reading is opening something already made rather than making it."""
    for page in (PAGES["learn"], PAGES["texts"]):
        assert "A targum is an interactive bilingual text" in page
        assert "A targum is a text you have built" not in page


@pytest.mark.parametrize(
    ("which", "has", "lacks"),
    [
        ("texts", 'id="library-list"', 'id="word-table"'),
        ("words", 'id="word-table"', 'id="phrase-list"'),
        ("phrases", 'id="phrase-list"', 'id="word-table"'),
    ],
)
def test_a_list_page_carries_its_own_list_and_no_other(which: str, has: str, lacks: str) -> None:
    """One template three times: the difference between them is which section renders."""
    page = PAGES[which]
    assert has in page
    assert lacks not in page
    assert 'id="carry"' not in page, "and none of them repeats the landing page"


def test_a_list_page_marks_learn_in_the_nav() -> None:
    """These are where Learn's lists go on, not places of their own — nothing in the nav
    points at them, so the nav goes on saying Learn."""
    for which in ("texts", "words", "phrases"):
        current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', PAGES[which])
        assert current == ["learn"], which


def test_the_suggestion_points_at_a_row_without_pressing_it() -> None:
    """Learn links here with an id in the hash. An unbuilt row is a button that starts
    spending, so arriving with an id marks the row and scrolls to it — it never presses
    it. A page that could be made to buy something by its own address is a hole."""
    library = (ASSETS / "library.js").read_text(encoding="utf-8")
    pointing = library[library.index("function pointAt") : library.index("find.value = view.find")]
    assert "scrollIntoView" in pointing
    assert 'classList.add("pointed")' in pointing
    assert "click()" not in pointing and "data-build" not in pointing


def test_which_hebrew_is_a_switch_rather_than_two_more_filter_pills() -> None:
    """Biblical and modern Hebrew are close to two languages, and which one somebody is
    learning is the first question this page asks. As pills it sat beside the kind filter
    with a second chip also saying "All", and the two rows read as one row of ten."""
    library = PAGES["library"]
    assert 'class="segmented" id="register-chips"' in library
    assert '<span class="switch-label">Hebrew</span>' in library, "and it says what it is"
    assert 'class="chips" id="register-chips"' not in library

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert '"register",\n        redraw,\n        "segment",' in source, "segments, not chips"


# -- bringing your own text ------------------------------------------------------


def test_the_upload_page_takes_a_text_three_ways() -> None:
    """A file, a link, or the text itself. Half of what anybody wants to read is already
    on their clipboard, and saving it to a file to hand it back is a step for nothing."""
    add = PAGES["add"]
    assert 'id="file"' in add and 'id="source"' in add and 'id="pasted"' in add

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert "function fromPaste(" in source, "pasted text goes through the one door"
    assert "btoa(unescape(encodeURIComponent(" in source, "and Hebrew survives the trip"


def test_the_upload_page_offers_a_translation_you_already_have() -> None:
    """A translation the reader has is a translation nobody has to make: the aligner
    lines it up, the same way the catalogue's published translations are lined up."""
    add = PAGES["add"]
    assert 'id="how"' in add and 'data-how="mine"' in add and 'data-how="make"' in add
    assert 'id="translation"' in add, "and somewhere to put it"

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert "body.translationName" in source and "body.translationContent" in source


def test_a_cover_is_drawn_for_an_upload_without_being_asked() -> None:
    """A shelf of pictures beats a shelf of letters and drawing one is cheap, so it is
    not a question: there is no tick, and every upload gets one."""
    add = PAGES["add"]
    assert "draw-cover" not in add, "the tick nobody was going to untick"

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    drawing = source[source.index('if (state.stage === "done")') :][:600]
    assert 'ask("/cover"' in drawing, "asked for every time"
    assert "checked" not in drawing, "and not off a control"

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    # After the text is readable, never before it. Nobody waits on a picture to read.
    drawing = source[source.index('if (state.stage === "done")') :][:800]
    assert 'ask("/cover"' in drawing


def test_the_upload_page_offers_only_the_pairs_that_have_been_taken_end_to_end() -> None:
    """Three languages in and two out, each saying how far along it is. The rest of the
    app can show eight; these are the ones an upload has actually been through."""
    add = PAGES["add"]
    said_in_page = html.unescape(add)
    for said in ("Hebrew (alpha)", "Aramaic (Experimental)", "Yiddish (Experimental)"):
        assert said in said_in_page, said
    assert "English (alpha)" in said_in_page
    assert "Russian (Experimental)" in said_in_page
    for gone in ("French", "Spanish", "German", "Latin", "Arabic"):
        assert f">{gone}" not in add, f"{gone} is not something an upload may ask for"


def test_the_upload_page_does_not_offer_to_guess_the_language() -> None:
    """It used to end the list with "work it out for me", which sent no language at all
    and left the server to detect one. A reader who does not know what they have is being
    asked to trust a guess they cannot check, on a build they are about to pay for."""
    add = PAGES["add"]
    assert "work it out for me" not in add
    assert 'value=""' not in add, "so the picker always sends a language"


def test_a_translation_can_be_pasted_as_well_as_dropped() -> None:
    """Whatever is true of the text is true of its translation: most of what anybody has
    is on a clipboard rather than in a file."""
    add = PAGES["add"]
    assert 'id="pasted-translation"' in add

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    within = source[source.index("function withTranslation") :][:700]
    assert "pasted-translation" in within and "fromPaste(" in within


def test_a_signed_in_reader_can_look_a_word_up() -> None:
    """Hosted, there is no start-up key: the session cookie is what lets a lookup through,
    and a page cannot read it. Gated on the key alone, the live site drew every look-up
    button disabled — "nothing saved" — and `g` did nothing, on the one deployment where
    somebody other than the owner would ever press it."""
    source = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function canAsk()" in source
    assert "window.TargumSync.who" in source, "the sync layer already knows who is signed in"
    assert "served && passKey" not in source, "the key alone is a single-user answer"
    assert "!served || !passKey" not in source, "the key alone is a single-user answer"


def test_a_card_opens_with_a_meaning_targum_already_holds() -> None:
    """Pressing `g` for a word whose meaning is sitting in the cache is a button between
    the reader and something that was already theirs."""
    source = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function peek(index, onDone)" in source
    assert "free: true" in source, "asked of the cache, never bought"
    assert "peek(index, function (found)" in source, "and the card asks before it offers the button"


def test_reader_links_are_percent_encoded() -> None:
    """A folder is named from a title, and a title can carry anything. The one that broke
    it had a raw `%` — a browser sent it as-is, and the proxy refused the request before
    targum saw it."""
    for name in ("library.js", "shelf.js", "learn.js", "add.js"):
        source = (ASSETS / name).read_text(encoding="utf-8")
        assert '"/reader/" + reader.name' not in source, name
        assert '"/reader/" + row.built.name' not in source, name
        assert '"/reader/" + job.reader)' not in source, name
        assert '"/reader/" + state.reader)' not in source, name
        assert "encodeURIComponent" in source, name


def test_every_page_with_the_header_can_follow_a_build() -> None:
    """The bell lives in the shared header (2026-09-11: notifications in the top corner,
    where a pill at the foot of the window used to be), and the script that draws it
    has to be on every page that carries it — or a build followed on Learn vanishes on
    Library."""
    strip = baked("building.js")
    body = strip[strip.index('getElementById("notices-open")') :][:60]
    for name, page in PAGES.items():
        if 'class="site-head"' not in page:
            continue
        assert 'id="notices"' in page and 'id="notices-panel"' in page, f"{name} has no bell"
        assert 'id="building"' not in page, f"{name} still carries the pill"
        assert body in page, f"{name} does not inline building.js"


def test_a_youtube_address_is_no_longer_turned_away_at_the_paste() -> None:
    """It was, for as long as the box would not fetch one: the page named the two doors
    that opened — the file itself, or targum on the reader's own machine — and stopped
    the request before it was made. The box fetches now, so a page that still refused
    would be refusing something that works, and the address goes to /prepare like any
    other link.
    """
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert "youtubeAddress" not in source, "nothing recognises it in order to refuse it"
    assert "YOUTUBE" not in source
    add = PAGES["add"]
    assert "YouTube links are not fetched here" not in add
    assert "run targum on your own computer" not in add
