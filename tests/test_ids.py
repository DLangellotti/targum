"""Names that have to survive a filesystem and a URL."""

from __future__ import annotations

from targum.ids import slug


def test_a_slug_carries_nothing_a_url_cannot() -> None:
    """A title with "60%" in it made a folder that Caddy refused to serve: `%` starts an
    escape, `%-מ` is not one, and the request never reached targum at all."""
    made = slug("צוקרברג תכנן לפטר 60% מהעובדים & נסוג #ברגע")
    for bad in "%#&":
        assert bad not in made, f"{bad!r} in {made}"
    assert "60-מהעובדים" in made, "the number stays, the sign goes"
    assert slug("Chapter 3: A & B") == "chapter-3-a-b"
