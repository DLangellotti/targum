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

#: The four modern registers what readers bring is sorted into by its source (David,
#: 2026-11-01; design.md §12, "What learners bring is counted in the tables, never kept").
#: Each is a yardstick of its own; none is a catalogue register today. The discovery
#: pool's public finds count into them too, as counts only (`tables.finds`, 2026-11-01).
SOCIAL = "social"
VIDEO = "video"
PODCASTS = "podcasts"
EVERYDAY = "everyday"

#: What readers bring that sorts into no register (David, 2026-11-01): "What learners
#: bring". Never a catalogue register and never a fold's: only `tables.imports.pool`
#: writes it, with no row below the floor of ten readers (`imports.FLOOR`).
IMPORTS = "imports"

#: The registers a yardstick is drawn from: the four the card shows first.
YARDSTICKS = (NEWS, BIBLE, LITERATURE, CONVERSATION)

#: The registers what readers bring may be sorted into, besides `IMPORTS`.
SORTED = (NEWS, SOCIAL, VIDEO, PODCASTS, EVERYDAY)

#: The registers the card's picker may offer: every one that has a list (David,
#: 2026-11-01). Each is still offered only where it has a list.
PICKER = (*YARDSTICKS, SOCIAL, VIDEO, PODCASTS, EVERYDAY, IMPORTS)


def pooled(register: str) -> str:
    """Where the pool files what readers brought of one register: `imports` for what
    sorts into none, `imports:<register>` otherwise, so their counts never mix with the
    public counts of the same register and the pool can delete all of them at once."""
    return IMPORTS if register == IMPORTS else f"{IMPORTS}:{register}"


def is_pooled(register: str) -> bool:
    """Whether a register is one only the imports pool writes."""
    return register == IMPORTS or register.startswith(f"{IMPORTS}:")


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
