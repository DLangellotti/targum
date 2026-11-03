"""The Russian interface's small things from the beta review's browser pass (2026-11-03,
`russian-oleh.md` part 2): each held where it is decided, so it cannot drift back."""

from __future__ import annotations

import re

from targum.render.builder import ASSETS, front_page
from targum.strings import catalogue


def test_the_front_doors_word_card_names_a_binyan_in_russian() -> None:
    """R30: the demo card listed "pa’al", "nif’al", "pi’el" in Latin above «пааль,
    настоящее». The names are Progress's («паал», «хифъиль»), one spelling everywhere."""
    script = (ASSETS / "landing.js").read_text(encoding="utf-8")
    assert '+ binyanName(b[0]) + "' in script
    said = catalogue("ru")
    for key in ("paal", "nifal", "piel", "pual", "hifil", "hufal", "hitpael"):
        assert said[f"landing.binyan.{key}"] == said[f"progress.gap.binyan.{key}"], key
    assert said["landing.card.pa-al-present"].startswith(said["progress.gap.binyan.paal"] + ",")
    assert said["landing.card.hif-il-present"].startswith(said["progress.gap.binyan.hifil"] + ",")
    page = front_page(language="ru")
    assert "hitpa’el" not in page and said["landing.binyan.hitpael"] in page


def test_progress_is_lower_case_beside_its_your() -> None:
    """R28: «Ваш Прогресс». The place's word is lower case beside «Ваш», and capital only
    where it stands alone."""
    sheet = (ASSETS / "chrome.css").read_text(encoding="utf-8")
    assert "html:lang(ru) .site-nav .nav-place { text-transform: lowercase; }" in sheet
    narrow = sheet[sheet.index("@media (max-width: 60rem) {") :]
    narrow = narrow[: narrow.index("\n}\n")]
    assert "html:lang(ru) .site-nav .nav-place { text-transform: none; }" in narrow


def test_a_short_month_does_not_end_a_sentence_twice() -> None:
    """R27: «…считаются с 3 нояб..»."""
    script = (ASSETS / "progress.js").read_text(encoding="utf-8")
    at = script.index('t("progress.words.since"')
    assert re.search(r"\}\)\.replace\(/\\\.\\\.\$/, \"\.\"\);", script[at : at + 400])


def test_a_weekly_rows_level_is_said_once() -> None:
    """R25: "Easy · 1,000 words" beside the title and «Лёгкий · 1 000 слов» under it."""
    script = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert 'if (parts.level && !(uiLanguage !== "en" && row.englishLang === uiLanguage))' in script
