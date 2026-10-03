"""/how: the hard parts of Hebrew, each solved on a real text (targum-internal#401).

The page's rules are the issue's: every section has an example, the examples are what
the pipeline made (`scripts/how_examples.py` copies them into `how.json`), and the page
impresses without confessing — no model, no prompt, no shortfall. These hold the page to
the half of that a test can see.
"""

from __future__ import annotations

import re

import pytest
from markupsafe import escape

from targum.render.builder import about_page, how_examples, how_page

#: Section ids, one per hard part the issue names, in its order.
PARTS = ("vowels", "spelling", "prefixes", "roots", "speech", "media", "aramaic")

#: What the page must never name: the models and vendors behind a stage, and the words
#: a page uses when it is admitting a stage falls short. The credits name DICTA, whose
#: licence asks for it, and only as DICTA.
UNSAID = (
    "dictabert",
    "menaked",
    "nakdimon",
    "whisper",
    "openai",
    "anthropic",
    "claude",
    "sonnet",
    "opus",
    "stanza",
    "prompt",
    "least sure",
    "accuracy",
    "error rate",
    "unreliable",
    "less reliable",
)


@pytest.fixture(scope="module")
def page() -> str:
    return how_page(address="https://targum.page")


def test_every_hard_part_has_its_section_and_its_example(page: str) -> None:
    for part in PARTS:
        section = re.search(rf'<section class="part" id="{part}">(.*?)</section>', page, re.S)
        assert section, f"no section for {part}"
        assert 'class="example' in section.group(1), f"{part} shows no example"
        assert 'lang="he"' in section.group(1) or 'lang="arc"' in section.group(1), part


def test_the_page_names_no_model_and_confesses_nothing(page: str) -> None:
    visible = re.sub(r"<style>.*?</style>", " ", page, flags=re.S).lower()
    for word in UNSAID:
        assert word not in visible, f"/how says {word!r}"


def test_the_examples_are_the_ones_written_down() -> None:
    """The page draws `how.json` and nothing typed into the template: each example's
    Hebrew is on the page as the script copied it."""
    examples = how_examples()
    page = how_page()
    assert str(escape(examples["vowels"]["pointed"])) in page
    assert str(escape(examples["vowels"]["plain"])) in page
    for pair in examples["homographs"]:
        letters = {card["letters"] for card in pair}
        assert len(letters) == 1, "a pair is two readings of the same letters"
        assert len({card["kind"] + card["meaning"] for card in pair}) == 2
    for word in examples["prefixes"]:
        assert word["parts"], f"{word['surface']} lost nothing"
        assert word["word"] in page
    patterns = [row["pattern"] for row in examples["roots"]["rows"]]
    assert len(patterns) >= 3, "one root across its patterns"
    wheres = {use["where"] for row in examples["roots"]["rows"] for use in row["uses"]}
    assert "weekly" in wheres and any(w.startswith("Genesis") for w in wheres)
    for line in examples["speech"]["sentences"]:
        times = [w["at"] for w in line["words"]]
        assert times == sorted(times), "a word is timed after the one before it"
    assert not re.search(r"[.,?!]", examples["speech"]["heard"]), "heard has no marks"
    assert examples["media"]["reel"]["tall"]
    assert examples["media"]["reel"]["poster"].startswith("data:image/webp;base64,")
    assert any(word["meaning"] for word in examples["aramaic"]["words"])


def test_the_page_fetches_nothing_and_needs_no_script(page: str) -> None:
    """Like every public page. And no `style=""`: the policy drops inline attributes."""
    assert "<script src" not in page
    assert not re.search(r'<img[^>]+src="http', page)
    assert not re.search(r'<[^>]+\sstyle="', page), "inline style attributes will not apply"
    assert 'type="checkbox" id="how-points"' in page, "the vowel switch works with no script"


def test_it_names_its_address_in_each_language(page: str) -> None:
    assert '<link rel="canonical" href="https://targum.page/how">' in page
    assert 'hreflang="ru" href="https://targum.page/how?lang=ru"' in page
    russian = how_page("ru", address="https://targum.page")
    assert '<html lang="ru">' in russian
    assert "Как targum читает иврит" in russian


def test_the_licences_that_ask_for_a_name_get_one(page: str) -> None:
    credits = re.search(r'<section class="part credits".*?</section>', page, re.S)
    assert credits
    for name in ("DICTA", "Open Scriptures", "Metsudah Chumash", "Vegan Friendly"):
        assert name in credits.group(0), name


def test_it_is_reached_from_the_foot_and_from_about(page: str) -> None:
    assert 'href="/how"' in about_page()
    assert 'href="/how"' in page
