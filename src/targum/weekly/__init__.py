"""The weekly: one issue of Hebrew news a week, written at three levels.

The half of this package that *serves* an issue is here and is open source. The half
that *makes* one — the source registry, the fact base and the compose loop — is content
generation, and content targum creates is proprietary. It is gitignored, it does not
ship in the wheel (hatchling leaves VCS-ignored files out), and it runs from a working
tree rather than on the box, which also keeps it clear of AGPL section 13.

With neither the private half nor an index present, everything here answers empty and
the weekly is simply absent.
"""

from __future__ import annotations
