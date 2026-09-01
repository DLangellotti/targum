"""The weekly Torah portion: a fixed corpus and a calendar that points at it.

The news weekly and this look alike on the page and are opposites underneath. The
weekly *writes* content every week and its archive accumulates. The Torah's corpus is
fixed and finite — the same 54 portions, forever — so nothing here generates anything.
The portions are cut once from the Tanakh already on the shelf, and the only moving
part is a pointer that says which one this Shabbat is.

What follows from that is the shape of the package:

* `calendar` answers "which reading is this Shabbat", for both schedules, including
  the weeks where they disagree. It is the only part that talks to the network, once
  a year, into a cache.
* `cut` turns a reading's verse ranges into a document with the seven aliyot as its
  sections.
* `build` does that for the whole cycle and writes the entries the library lists.
"""

from __future__ import annotations

from .calendar import Aliyah, Reading, ReadingKind, Schedule, current, for_shabbat

__all__ = [
    "Aliyah",
    "Reading",
    "ReadingKind",
    "Schedule",
    "current",
    "for_shabbat",
]
