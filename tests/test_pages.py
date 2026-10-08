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
    library_page,
    list_page,
    progress_page,
    welcome_page,
    you_page,
)

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "templates"

PAGES = {
    "welcome": welcome_page("k"),
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
    assert 'id="given"' in add, "the one box a link or a text is typed into"
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
    home = PAGES["texts"]
    assert 'id="source"' not in home and 'id="drop"' not in home, "no form on the front door"
    assert home.count('type="file"') == 0, "the + is in the framed conversation (2026-09-11)"
    # One hidden input behind the +, and one behind Speak for a device that cannot record
    # live, which opens its own recorder (2026-09-14).
    assert EMBED.count('type="file"') == 2, "a hidden input behind the + and one behind Speak"
    assert 'id="chat-voice" hidden accept="audio/*" capture' in EMBED


def test_the_library_carries_nothing_personal() -> None:
    """It answers to a stranger and to a signed-in reader with the same thing now, which
    is what makes it coherent. Anything belonging to somebody lives on Learn."""
    library = PAGES["library"]
    assert 'id="catalogue"' in library, "the catalogue is the page"
    assert 'id="library-list"' not in library, "the shelf moved to Learn"
    assert 'id="trash-list"' not in library, "and so did the trash"
    assert 'href="/add"' in library, "but it says where to go when nothing fits"


def test_home_carries_what_belongs_to_the_reader() -> None:
    """Home is Your targums since 2026-10-08 (design.md §12): Continue at the top, the
    shelf under it, one text to try next and the upload beside it. Learn's count, sheet
    and row of doors went with Learn."""
    home = PAGES["texts"]
    assert 'id="continue-cards"' in home, "what you came back for"
    assert 'id="library-list"' in home and 'id="trash-list"' in home, "the shelf and the trash"
    assert 'id="try-next"' in home and 'class="upload-card"' in home
    assert home.index('id="continue"') < home.index('id="shelf-panel"'), "Continue leads"
    for gone in ('id="known-line"', 'id="carry"', 'id="doors"', 'id="carry-frame"'):
        assert gone not in home, f"{gone} went with Learn"
    assert 'id="word-table"' not in home and 'id="phrase-list"' not in home
    assert 'id="catalogue"' not in home, "the catalogue has its own page"


def test_the_arrival_is_a_page_of_its_own() -> None:
    """The questions a new reader is asked, on `/welcome`, and nothing of Learn's around
    them (design.md §12, 2026-10-08)."""
    welcome = PAGES["welcome"]
    assert 'id="arrival"' in welcome and 'id="arrival-doors"' in welcome
    assert "TargumArrival" in welcome
    for gone in ('id="carry"', 'id="doors"', 'id="known-line"', 'id="library-list"'):
        assert gone not in welcome, gone


def test_the_numbers_belong_to_the_progress_page() -> None:
    """Learn used to carry a smaller, worse copy of both charts. One place counts, and it
    is the page somebody goes to on purpose."""
    home, progress = PAGES["texts"], PAGES["progress"]
    assert 'id="tiles"' not in home and 'id="growth"' not in home
    assert 'id="growth"' in progress


def test_the_progress_page_is_only_the_numbers() -> None:
    """No table, no list, no export. Everything a reader works on moved to Learn, and a
    page that is half metrics and half working surface is neither."""
    progress = PAGES["progress"]
    for gone in ('id="word-table"', 'id="phrase-list"', 'id="search"', 'id="export-all"'):
        assert gone not in progress, f"{gone} belongs to Learn now"
    assert 'id="ledger"' in progress and 'id="milestones"' in progress


def test_the_progress_page_says_it_is_empty_above_its_foot() -> None:
    """The empty state was drawn after the foot's include, so a reader with nothing
    marked saw the site's foot and then, under it, the page's one line (2026-09-28)."""
    progress = PAGES["progress"]
    assert progress.index('id="nothing"') < progress.index('<footer class="site-footer"')


# -- the nav -------------------------------------------------------------------


def test_every_page_carries_the_same_four_places() -> None:
    """One nav file, because copies drift — they had drifted into three different orders
    once already. Five from 2026-09-24 until 2026-10-08, when Learn was taken apart and
    Your targums became home (design.md §12): Your targums, Library, Your Progress, and
    Upload last."""
    for name, page in PAGES.items():
        found = re.findall(r'data-nav="(\w+)"', page)
        assert found == ["texts", "library", "progress", "add"], name


#: Reached from somewhere other than the nav — a profile is not one of the places you
#: can be, it is who you are while you are in one of them.
NOT_IN_THE_NAV = {"you", "words", "phrases", "welcome", "chat"}


def test_the_nav_marks_where_you_are() -> None:
    for name, page in PAGES.items():
        current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', page)
        if name in NOT_IN_THE_NAV:
            assert current == [], f"{name} is not a nav destination and marks nothing"
            continue
        assert current == [name], f"{name} should mark itself and nothing else"


def test_bringing_a_text_is_the_box_and_a_place() -> None:
    """Add used to be first in the nav, then the corner, then from 2026-09-06 only the
    `+` on the box. Since 2026-09-13 it is both: the `+` brings a file while asking, and
    the page is the last place in the nav, the one that keeps its `+` at a desk."""
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        assert 'id="chat-bring"' in page and 'id="chat-file"' in page, name
        assert 'class="upload' not in page, name
    assert 'id="talk-frame"' in PAGES["texts"], "every page carries the drawer that frames it"
    bring = (ASSETS / "bring.js").read_text(encoding="utf-8")
    assert 'keyed("/add")' in bring, "the Add page is one link away, on the card"
    order = re.findall(r'data-nav="(\w+)"', PAGES["texts"])
    assert order.index("texts") == 0, "home leads"
    add = re.search(r'<a href="/add" data-nav="add"[^>]*>(.*?)</a>', PAGES["texts"])
    # Upload, never Add (design.md §12, 2026-10-08).
    assert add and 'class="nav-glyph"' in add.group(1) and "<span>Upload</span>" in add.group(1)


def test_every_desk_page_wears_the_chrome_s_face() -> None:
    """design.md §13 (2026-09-11): the chrome's face is carried in every page that wears
    the bar; the reader never loads it. Home frames no reader since 2026-10-08."""
    home = PAGES["texts"]
    # The sheet went with Learn (2026-10-08): home frames no reader.
    assert 'id="carry-frame"' not in home and 'id="talk-title"' not in home
    for name, page in list(PAGES.items()) + [("embed", EMBED)]:
        assert page.count('font-family:"Source Sans 3"') == 2, (
            f"{name}: the chrome face, upright and italic"
        )
    from targum.render.builder import ASSETS

    reader = (ASSETS / "reader.css").read_text(encoding="utf-8")
    assert "--chrome:" in reader and "--ground:" in reader and "--teal:" in reader


def test_the_command_palette_is_on_every_page() -> None:
    """2026-09-11: ⌘K, or the search in the bar, finds a place, a text, a series or a
    conversation and goes there. Its markup and script ride in the bar's partial."""
    for name, page in PAGES.items():
        if 'class="site-head"' not in page:
            continue
        assert 'id="palette"' in page and 'id="palette-find"' in page, name
        assert 'id="palette-open"' in page and "TargumPalette" in page, name


def test_talk_to_targum_is_a_pill_on_every_page_that_opens_the_conversation() -> None:
    """2026-09-11: "'talk to targum' can be in the sticky CTA on every page that opens up
    for you — doesn't actually have to live on any page". The pill and the drawer ride in
    the bar's partial, the drawer frames the conversation page without its bar and loads
    nothing until opened, and the conversation page itself carries the drawer's script
    but hides the pill, since it is the conversation."""
    for name, page in PAGES.items():
        if 'class="site-head"' not in page:
            continue
        assert 'id="talk-open"' in page and 'id="talk-drawer"' in page, name
        assert 'id="talk-frame"' in page and "TargumTalk" in page, name
        assert 'data-src="/chat?embed=1&amp;k=k"' in page and ' src="/chat?embed=1' not in page, (
            f"{name}: loaded when opened, not before"
        )
        assert 'id="composer"' not in page or name == "chat", f"{name}: the box is in the frame"
    assert 'class="chat embed"' in EMBED and '<base target="_top">' in EMBED
    assert 'class="site-head"' not in EMBED and "data-nav=" not in EMBED, "no bar, no foot"
    assert 'id="composer"' in EMBED and 'id="chat-thread"' in EMBED and "TargumChat" in EMBED
    assert 'class="chat"' in PAGES["chat"] and "<base " not in PAGES["chat"]
    assert 'id="chat-reading"' in EMBED, "and it can be told where the reader is"


def test_the_box_is_the_front_door() -> None:
    """The conversation page carries the box, and the drawer frames the same one from the
    same file: one field, the `+`, Speak, Send."""
    for name, page in (("chat", PAGES["chat"]), ("embed", EMBED)):
        for control in ('id="chat-bring"', 'id="chat-mic"', 'id="chat-send"', 'id="chat-said"'):
            assert page.count(control) == 1, f"{name}: {control} once"


def test_the_box_s_actions_are_glyphs_with_the_word_as_their_label() -> None:
    """Since 2026-09-10 (targum-internal#235) Speak, Send and Hear are drawn, not written:
    a microphone, an arrow, a loudspeaker from one sprite, each to §7 — sixteen pixels,
    no fill, a stroke at 1.4 with round caps — and the word kept as the label, so a
    screen reader says what the button used to say. The `+` stays typed, as §7 keeps
    typed characters as themselves. A file joined them on 2026-09-13, for Choose files
    on the Add page's box (targum-internal#249)."""
    sprite = (TEMPLATES / "_glyphs.html.j2").read_text(encoding="utf-8")
    symbols = re.findall(r'<symbol id="glyph-(\w+)" viewBox="([^"]+)">', sprite)
    assert sorted(name for name, _ in symbols) == ["file", "hear", "mic", "send", "stop"]
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
    assert 'button.setAttribute("aria-label", t("chat.hear", "Hear"))' in chat
    assert 'glyph("hear")' in chat
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


def test_your_words_stand_behind_the_account_with_the_checklist_and_the_phrases() -> None:
    """2026-09-11: "words/phrases should be moved into a dedicated page you access by
    clicking on your picture in the top right", and the checklist "after onboarding
    accessible only on the words/phrases page". The account panel on every page links to
    Your Words; the page holds the words, the may-already-know checklist and the
    phrases, in that order; Learn holds none of them."""
    words = PAGES["words"]
    assert (
        'id="word-table"' in words and 'id="claim-panel"' in words and 'id="phrase-list"' in words
    )
    assert (
        words.index('id="word-table"')
        < words.index('id="claim-panel"')
        < words.index('id="phrase-list"')
    )
    assert "Words you may already know" in words and "TargumClaim" in words
    assert 'id="claim-body"' in words, "the script builds the table into the panel's body"
    for name, page in PAGES.items():
        if 'class="site-head"' not in page:
            continue
        assert 'class="to-you" href="/words"' in page, f"{name}: Your Words is in the account panel"
    # Your Words keeps the grid itself. Learn offered it once on the way in until Learn was
    # taken apart (2026-10-08); home carries none of it.
    assert 'id="claim-panel"' not in PAGES["texts"] and 'id="claim-here"' not in PAGES["texts"]


def test_your_subscriptions_stand_on_the_profile_and_every_page_hears_them() -> None:
    """2026-09-11: "subscriptions should be under the profile dropdown (perhaps on /you)
    — let's keep the main pages as simple as possible". The row is a panel on the
    profile, the account panel links to it, the Library carries nothing of it, and the
    script that asks is in the bar on every page so the bell hears a landed instalment."""
    you = PAGES["you"]
    assert 'id="subscriptions"' in you and 'id="series"' in you and "Following" in you
    assert 'id="subscriptions"' not in PAGES["library"] and 'id="series"' not in PAGES["texts"]
    for name, page in PAGES.items():
        if 'class="site-head"' in page:
            assert 'class="to-you" href="/you#subscriptions"' in page, name
            assert "TargumFollow" in page, f"{name}: the bell hears a landed instalment"
            assert page.index("TargumFollow") < page.index('getElementById("notices-open")'), name


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


def test_home_is_honest_when_there_is_nothing() -> None:
    """A reader with nothing yet is told what will appear, with one to start with and the
    upload under it (FirstRun); a shelf that could not be asked for says so, rather than
    telling a reader with a shelf that they have nothing (2026-09-14)."""
    home = PAGES["texts"]
    assert "Nothing here yet. What you open or upload appears here." in home
    assert 'href="/add"' in home, "the upload"
    failed = home[home.index('id="nothing"') :]
    assert "We couldn" in failed and "load your texts" in failed


def test_an_empty_shelf_still_draws_the_page() -> None:
    """The first alpha reader's first words were "no idea where to start", on a page that
    hid everything when the shelf was empty. Home's empty line and its one to start with
    live inside `#page`, and the script shows `#page` whatever the shelf holds."""
    from targum.render.builder import ASSETS

    home = PAGES["texts"]
    assert home.index('id="page"') < home.index('id="first-home"') < home.index('id="try-next"')
    script = (ASSETS / "yours.js").read_text(encoding="utf-8")
    assert 'getElementById("page").hidden = false' in script


# -- the charts are shared, not copied ------------------------------------------

ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"


def test_the_growth_chart_is_defined_once() -> None:
    """Two pages draw it. A second copy is a chart that drifts — the words page would
    keep a fix and Learn would not, and nobody would notice for months.
    """
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert "function drawGrowth(" in charts
    for page in ("progress.js", "arrival.js"):
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


@pytest.mark.parametrize("page", ["progress", "welcome"])
def test_a_page_that_draws_charts_loads_them_first(page: str) -> None:
    """The first version of this said `"charts.js" in html or "TargumCharts" in html`,
    which passes on any page whose own script merely *mentions* the global — so Learn
    shipped without charts.js at all and the assertion stayed green. Look for the
    definition, not the name."""
    html = PAGES[page]
    charts = baked("charts.js")
    body = charts[charts.index("window.TargumCharts =") :][:80]
    assert body in html, f"{page} does not inline charts.js"
    own = baked({"welcome": "arrival.js"}.get(page, f"{page}.js"))[:200]
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


def test_a_refused_upload_says_what_the_server_said_not_check_your_connection() -> None:
    """Copy audit, 2026-09-28 (Q3). A picture over its size, a protected file or a full
    recording allowance came back as a sentence from the upload door, and Continue's
    catch threw it away for "We couldn't reach targum. Check your connection". The door
    rejects with the server's `error`, a string; a failed fetch rejects with an object."""
    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    press = source[source.index("go.onclick = function") :]
    caught = press[press.index("    prepared\n") :][:1800]
    assert ".catch(function (why)" in caught
    assert 'typeof why === "string"' in caught
    assert caught.index('typeof why === "string"') < caught.index('t("add.unreachable"')
    bring = (ASSETS / "bring.js").read_text(encoding="utf-8")
    assert "if (opened.error) throw opened.error;" in bring, "the door rejects with its sentence"


# -- one catalogue, and what each text is ----------------------------------------


def test_the_library_is_one_list() -> None:
    """There were two shelves with a tab switcher between them. A reader had to know
    which room a text was in before they could find it, which is backwards for the one
    page whose whole job is finding something."""
    library = PAGES["library"]
    assert 'id="shelves"' not in library, "no room switcher"
    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert "SHELVES" not in source and "drawShelves" not in source
    # The name came back on 2026-09-19 (design.md §12, targum-internal#340) and the rooms
    # did not: the Beit Midrash is a tab over the same list, which is the thing this test
    # was always protecting. It draws with the list's own rows and cards, it has no
    # address of its own for a text, and `test_library_js.py` holds it to every row being
    # a row under All texts too.
    assert "/beit-midrash/" not in library and "/beit-midrash/" not in source
    assert source.count("function card(row)") == 1 and source.count("function draw(row") == 1


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
    and their trash. With nothing else on the page it only repeated the h1.

    The one h2 is the Weekly portion shelf's (targum-internal#411): a shelf of its own
    above the list, which says something the h1 does not."""
    library = PAGES["library"]
    assert "Picked for you" not in library
    assert re.findall(r"<h2\b[^>]*\bid=\"([^\"]+)\"", library) == ["portions-head"]
    assert len(re.findall(r"<h2\b", library)) == 1


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


@pytest.mark.parametrize("page", ["progress", "arrival"])
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


def test_the_library_is_browsed_as_cards_and_sifted_as_a_list() -> None:
    """Both shapes, over one list (design.md §12, 2026-09-17).

    This asserted for months that "the card grid is gone", and it was right: a card
    cannot be sorted, and the grid it replaced could not answer "which of these can I
    read". The page is browsed now, so the grid is back — and the complaint that retired
    it is answered rather than forgotten, because the sortable table is still here and is
    one press away.
    """
    library = PAGES["library"]
    for control in ("find", "register-chips", "kind-chips", "length", "difficulty"):
        assert f'id="{control}"' in library, f"the library cannot filter by {control}"
    assert 'id="rows-head"' in library, "the columns still sort"
    assert 'id="catalogue"' in library, "and the table is still a table"
    assert 'id="cards"' in library, "and the grid is what it opens in"
    assert 'id="shape"' in library, "with one control to change between them"
    # What it is browsed by, and how much of it is shown: the two the browse view adds.
    assert 'id="subject-chips"' in library, "the subjects are the row it browses by"
    assert 'id="said"' in library, "and the line that says how far it is narrowed"


def test_the_library_is_everyone_s_and_your_targums_is_yours() -> None:
    """design.md §12, "Yours and everyone's" (2026-09-25). The Library had a Your
    uploads tab, which listed what Your targums already listed. It is gone; the tab strip
    stays for the Beit Midrash."""
    library = PAGES["library"]
    assert 'id="where"' in library and 'role="tablist"' in library
    assert 'id="access"' not in library, "the Access filter stays gone too"

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert '["library", t("library.where.library", "All texts")]' in source
    assert "library.where.mine" not in source
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
    for page in ("library.js", "shelf.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function thumb(" not in source, f"{page} should use the shared tile"
        assert "TargumCovers.tile(" in source, f"{page} does not draw one"
    # Home draws its pictures through the one helper (targum-internal#429 swaps it).
    home = (ASSETS / "home.js").read_text(encoding="utf-8")
    assert "covers.picture(" in home and "function tile(" not in home


@pytest.mark.parametrize(("page", "script"), [("library", "library.js"), ("texts", "home.js")])
def test_a_page_that_draws_covers_loads_them_first(page: str, script: str) -> None:
    html = PAGES[page]
    covers = baked("covers.js")
    body = covers[covers.index("function tile(") :][:60]
    assert body in html, f"{page} does not inline covers.js"
    own = baked(script)[:200]
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


def test_home_holds_the_whole_shelf() -> None:
    """Learn capped its shelf and pointed at Your targums for the rest; home is Your
    targums, so the whole shelf is on it, under Continue (2026-10-08)."""
    home = PAGES["texts"]
    assert 'id="library-list"' in home and 'id="doors"' not in home


def test_nothing_on_home_folds() -> None:
    """Phase 2 (2026-09-11): a shelf is not worth a control to put away."""
    home = PAGES["texts"]
    assert home.count('class="fold"') == 0


def test_the_word_targum_is_defined_where_somebody_meets_it() -> None:
    """The product calls a built text a targum everywhere and had never once said what
    one is. Home drew a definition from 2026-09-26 until 2026-10-08, when the FirstRun
    boards gave it to the arrival's welcome, which says what targum is before anything
    is asked (design.md §12)."""
    welcome = PAGES["welcome"]
    assert "with a translation beside every line" in welcome
    assert 'class="defined-example"' not in PAGES["texts"]


@pytest.mark.parametrize(
    ("which", "has", "lacks"),
    [
        ("texts", 'id="library-list"', 'id="word-table"'),
        ("words", 'id="word-table"', 'id="library-list"'),
        ("phrases", 'id="phrase-list"', 'id="word-table"'),
    ],
)
def test_a_list_page_carries_its_own_list_and_no_other(which: str, has: str, lacks: str) -> None:
    """One template three times: the difference between them is which section renders."""
    page = PAGES[which]
    assert has in page
    assert lacks not in page
    assert 'id="carry"' not in page, "and none of them repeats the landing page"


def test_your_targums_marks_itself_in_the_nav() -> None:
    """Your targums has its own place since 2026-09-24 (design.md §12). Your words and
    phrases are reached from the account and mark no place: a nav that lit Learn on them
    said the reader was somewhere they were not (2026-09-14)."""
    current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', PAGES["texts"])
    assert current == ["texts"]
    for which in ("words", "phrases"):
        current = re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', PAGES[which])
        assert current == [], which


def _body_of(source: str, opening: str) -> str:
    """One function's source, by counting its braces.

    This used to be a slice between two landmarks — `function pointAt` and the next line
    that happened to follow it — and a block inserted between them put `ask(` inside the
    slice and failed a test about a function that does not call it. A function's body is
    the thing being asserted about, so the body is what this returns.
    """
    start = source.index(opening)
    depth = 0
    for at in range(source.index("{", start), len(source)):
        if source[at] == "{":
            depth += 1
        elif source[at] == "}":
            depth -= 1
            if depth == 0:
                return source[start : at + 1]
    raise AssertionError(f"{opening} never closes")


def test_the_suggestion_points_at_a_row_without_pressing_it() -> None:
    """Learn and `/open/<id>` both link here with an id in the hash. An unbuilt row is a
    button that starts spending, so arriving with an id marks the row and scrolls to it —
    it never presses it. A page that could be made to buy something by its own address is
    a hole.

    Since targum-internal#313 an id may arrive as `build:<id>`, which additionally puts
    the row's own press under the reader's hand. Focused, not pressed, and not quoted
    either: this used to be checked by forbidding the words `data-build` outright, and
    that was a proxy for the rule rather than the rule. What must never appear is
    anything that *fires* the button.
    """
    library = (ASSETS / "library.js").read_text(encoding="utf-8")
    pointing = _body_of(library, "function pointAt")
    assert "scrollIntoView" in pointing
    assert 'classList.add("pointed")' in pointing
    # Nothing here presses anything, by any of the names a press goes by.
    for firing in ("click()", ".submit(", "dispatchEvent", "requestSubmit"):
        assert firing not in pointing, f"pointAt must not fire a control: {firing}"
    # And nothing here asks the server for anything either — a quote costs nothing today
    # and a page that requests one because of what was in an address is one source type
    # away from spending on a link somebody followed.
    for asking in ("ask(", "fetch(", "build("):
        assert asking not in pointing, f"pointAt must not call {asking}"
    assert "focus(" in pointing, "it does put the press under their hand"


def test_which_hebrew_is_a_switch_rather_than_two_more_filter_pills() -> None:
    """Biblical and modern Hebrew are close to two languages, and which one somebody is
    learning is the first question this page asks. As pills it sat beside the kind filter
    with a second chip also saying "All", and the two rows read as one row of ten."""
    library = PAGES["library"]
    assert 'class="segmented" id="register-chips"' in library
    assert '<span class="switch-label">Which Hebrew</span>' in library, "and it says what it is"
    assert 'class="chips" id="register-chips"' not in library

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert '"register",\n        redraw,\n        "segment",' in source, "segments, not chips"


# -- bringing your own text ------------------------------------------------------


def test_the_upload_page_takes_anything_in_one_box() -> None:
    """A file, a link, or the text itself — and since 2026-09-13 in one box rather than
    three to choose between (design.md §12, targum-internal#249). Half of what anybody
    wants to read is already on their clipboard, and saving it to a file to hand it back
    is a step for nothing."""
    add = PAGES["add"]
    assert 'id="file"' in add and 'id="given"' in add
    assert 'id="source"' not in add and 'id="pasted"' not in add, "one box, not three"
    accepted = re.search(r'id="file" multiple\s+accept="([^"]+)"', add)
    assert accepted, "the box's file input takes several files"
    for kind in (".epub", ".pdf", ".srt", ".vtt", ".jpg", ".mp3", ".opus", ".mp4"):
        assert kind in accepted.group(1), f"any medium: {kind}"

    source = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert "function fromPaste(" in source, "pasted text goes through the one door"
    assert "btoa(unescape(encodeURIComponent(" in source, "and Hebrew survives the trip"


def test_a_description_is_said_in_the_conversation_by_the_reader_s_press() -> None:
    """A sentence about what the reader wants is a turn of conversation, not a text to
    price (2026-09-13, targum-internal#249). Ask targum hands it to the talk drawer, and
    the framed conversation says it only when it came from its own parent on this origin
    — the model is never the one who sends it, and no other page can."""
    add = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert "window.TargumTalk.say(read.text)" in add, "Ask targum is the reader's press"
    go = add[add.index("go.onclick") :]
    assert 'read.kind !== "link"' in go, "Continue never prices a description"

    talk = (ASSETS / "talk.js").read_text(encoding="utf-8")
    assert "say: say" in talk and '"targum:say"' in talk

    chat = (ASSETS / "chat.js").read_text(encoding="utf-8")
    listener = chat[chat.index('window.addEventListener("message"') :][:1200]
    assert "event.origin !== window.location.origin || event.source !== window.parent" in listener
    assert 'data.type === "targum:say"' in listener, "said only through the checked listener"


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
    """Six languages in and two out, each saying how far along it is — French, Russian
    and Italian joined Hebrew, Aramaic and Yiddish on 2026-09-13. These are the ones an
    upload has actually been through."""
    add = PAGES["add"]
    said_in_page = html.unescape(add)
    for said in (
        "Hebrew (alpha)",
        "Aramaic (Experimental)",
        "Yiddish (Experimental)",
        "French (Experimental)",
        "Italian (Experimental)",
    ):
        assert said in said_in_page, said
    assert "English (alpha)" in said_in_page
    assert "Russian (Experimental)" in said_in_page
    for gone in ("Spanish", "German", "Latin", "Arabic"):
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
    for name in ("library.js", "shelf.js", "home.js", "add.js"):
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


def test_your_words_carries_the_fold_and_promises_nothing_by_it() -> None:
    """What to work on (targum-internal#103): the words flagged and never come back to,
    above the table they are also in.

    It starts hidden, because a reader with nothing to work on sees no fold at all —
    not an empty state and not an invitation — and `lists.js` is what decides.
    """
    words = PAGES["words"]
    assert 'id="work-on"' in words and 'id="work-rows"' in words
    assert 'id="work-on" hidden' in words, "hidden until there is something in it"
    assert "What to work on" in words, "a question answered, not an instruction"

    # And nothing that schedules, counts or chases. "if smth gonna ping me or bother me
    # like duolingo I'll fucking delete it" — Dmitry Z, 2026-09-16, in the same minute he
    # asked for the list itself.
    fold = words[words.index('id="work-on"') : words.index('id="word-table"')]
    for chasing in ("due", "streak", "goal", "reminder", "review", "overdue"):
        assert chasing not in fold.lower(), f"the fold must not say {chasing!r}"


def test_the_fold_stands_on_the_words_page_alone() -> None:
    """Both, and nowhere else (David, 2026-09-18) — until Learn, the other half of "both",
    was taken apart on 2026-10-08. The fold is the words page's again; Your Progress's
    "what next" is where it is to be met next (design.md §12)."""
    assert 'id="work-on"' in PAGES["words"]
    for name in ("progress", "phrases", "texts", "welcome"):
        assert 'id="work-on"' not in PAGES[name], name


def test_the_key_is_set_before_any_script_that_reads_it() -> None:
    """targum-internal#343, found by the pre-deploy QA of 2026-09-20. `building.js` in the
    `<head>`, and the pill, the followed series and the palette in the nav, each read
    `window.TARGUM_KEY` once, as they load. The page set it at the foot of the body — so on
    a local serve they held an empty key for the life of the page, and `/jobs`, `/series`,
    `/account/follows` and `/chat/list` were refused on every desk page. Four console
    errors a page is also how a real one hides.

    Asked of the built pages rather than of the templates: the nav's scripts arrive by an
    include, which is how a template-only check would have missed three of the four.
    """
    for name, built in PAGES.items():
        if 'window.TARGUM_KEY = "' not in built:
            continue
        key_at = built.index('window.TARGUM_KEY = "')
        reads = [m.start() for m in re.finditer(r"window\.TARGUM_KEY \|\|", built)]
        assert reads, f"{name} sets a key nothing reads"
        assert key_at < min(reads), f"{name}: a script reads the key before the page sets it"
