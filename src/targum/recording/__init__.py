"""Recordings of texts the library already serves.

Public here, private on disk. The code that finds a recording and puts it in a reader is
in the repository; the recordings themselves are content, and content does not enter a
public repository — the same split `catalogue.py` and the dialogues are on.

What makes this its own thing rather than part of the dialogue package: a dialogue is
written here and voiced here, so its audio and its text are one artifact. A recording is
somebody else's reading of a text that already existed, aligned to it afterwards. It has
a reader to credit, a licence to carry, and it can be replaced without the text changing.
"""

from .models import Part, Recording

__all__ = ["Part", "Recording"]
