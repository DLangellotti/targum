"""Which register a text's counts go under (targum-internal#577).

From the catalogue entry, by the rule in the spec (`docs/language-tables-2026-10-30.md`
in targum-internal): four registers a reader's card is measured against, and every other
text under its catalogue register, so no row is lost.
"""

from __future__ import annotations

NEWS = "news"
BIBLE = "bible"
LITERATURE = "literature"
CONVERSATION = "conversation"

#: The conversations targum writes itself (`dialogue:` sources).
SCENES = "scenes"
#: The weekly, which a model writes too, under its own name for the same reason.
WEEKLY = "weekly"
#: A text the catalogue does not file and no rule above names.
UNFILED = "unfiled"

#: The registers a yardstick is drawn from: the four the card shows.
YARDSTICKS = (NEWS, BIBLE, LITERATURE, CONVERSATION)

#: Where targum's own scenes are counted. Open question 3 of the spec, not yet answered:
#: the proposal is that model-written Hebrew stays out of every yardstick, counted only
#: for the generator's own audit. Set this to CONVERSATION to count them as conversation.
SCENES_COUNT_AS = SCENES

_LITERATURE_KINDS = frozenset({"novel", "story", "play", "prose"})
_CONVERSATION_KINDS = frozenset({"dialogue", "talk"})


def register_of(source: str) -> str:
    """The register a text's counts are filed under, from its source."""
    if source.startswith("dialogue:"):
        return SCENES_COUNT_AS
    if source.startswith("weekly:"):
        return WEEKLY
    from .. import catalogue

    try:
        entry = catalogue.matching(source)
    except Exception:  # noqa: BLE001 - a private catalogue is absent on a public checkout
        entry = None
    if entry is None:
        return UNFILED
    tags = {str(tag) for tag in entry.tags}
    kind = str(entry.kind)
    era = str(entry.register)
    if "journalism" in tags or (kind == "article" and era == "modern"):
        return NEWS
    if "tanakh" in tags:
        return BIBLE
    if kind in _LITERATURE_KINDS and era == "revival":
        return LITERATURE
    if kind in _CONVERSATION_KINDS and era == "modern":
        return CONVERSATION
    return era or UNFILED
