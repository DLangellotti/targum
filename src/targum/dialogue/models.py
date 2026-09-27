"""What a dialogue is.

Small on purpose. A scene is a title, a cast and a list of turns; everything a reader
needs to open it is here, and everything about how it was made is not.

**The cast carries gender, and it is not decoration.** Hebrew writes לך for both "to you"
addressing a man and addressing a woman, and nothing in the letters decides which. The
diacritizer guesses, and guesses masculine every time: on a hundred dialogues it pointed
thirty-seven lines for the wrong listener. It cannot do better, because the answer is not
in the sentence — it is in who is standing there. So the room is written down, and the
pointing is checked against it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Which of the two is speaking. Two-handers only: every scene on the shelf is two people,
#: and a third would need the reader to tell three voices apart, which is a different
#: design and not one anything asks for yet.
Who = Literal["A", "B"]

Gender = Literal["m", "f"]


class Speaker(BaseModel):
    """One side of a scene: a synthesised voice, and the gender the Hebrew agrees with."""

    voice: str
    gender: Gender
    #: What the reader calls them, where a scene wants names rather than A and B.
    name: str = ""


class Cast(BaseModel):
    A: Speaker
    B: Speaker

    def other(self, who: Who) -> Speaker:
        """Whoever is being spoken to — the one whose gender the address forms take."""
        return self.B if who == "A" else self.A


class Turn(BaseModel):
    """One line: who says it, what they say, and when it is said."""

    who: Who
    text: str
    #: The published translation of this line. Written with the scene rather than bought
    #: from a model, because a dialogue is authored and its English is authored with it.
    english: str = ""
    #: And the same line in any other language targum speaks, by code
    #: (targum-internal#288). Authored like the English and carried with the scene, not
    #: bought at build time: a scene is content, and content a reader meets is reviewed
    #: before it ships. Empty for every scene written before this, which `said_in` reads
    #: as "say it in English" — the same fallback the catalogue's own names make.
    said: dict[str, str] = Field(default_factory=dict)

    def said_in(self, language: str) -> str:
        """This line's translation in `language`, English where there is none."""
        code = language.split("-")[0].lower()
        return self.said.get(code) or self.english

    #: Where this line sits in the scene's audio, in seconds. `None` where the line has no
    #: audio — a scene voiced before the line was added, or a synthesis that failed. A
    #: reader shows silence there rather than the wrong line's sound.
    start: float | None = None
    end: float | None = None

    @property
    def voiced(self) -> bool:
        return self.start is not None and self.end is not None


class Dialogue(BaseModel):
    """A scene, its cast, and its turns in order."""

    id: str
    title: str
    english: str
    #: One sentence on what happens, for the shelf. Not shown inside the reader: a scene
    #: that has to be explained before it is read has not been written well enough.
    gloss: str = ""
    #: The scene's own name and its one sentence, in any other language targum speaks
    #: (targum-internal#288). `named` answers `english`, `glossed` answers `gloss`; both
    #: are empty for every scene written before this and fall back to what they had.
    named: dict[str, str] = Field(default_factory=dict)
    glossed: dict[str, str] = Field(default_factory=dict)
    #: Which rung. 1 is six turns of present tense; 6 is forty and a register a learner
    #: meets in an office and nowhere else.
    level: int = 1
    cast: Cast
    turns: list[Turn] = Field(default_factory=list)
    #: The scene's audio, named relative to the dialogue's own directory so the same
    #: folder can be copied between machines without rewriting anything.
    audio: str = ""

    def name_in(self, language: str) -> str:
        """What this scene is called in `language`, English where it has no name yet."""
        return self.named.get(language.split("-")[0].lower()) or self.english

    def gloss_in(self, language: str) -> str:
        """Its one sentence in `language`, English where it has none."""
        return self.glossed.get(language.split("-")[0].lower()) or self.gloss

    @property
    def said_languages(self) -> set[str]:
        """Every language this scene is fully written in — every turn, not some of them.

        A scene half in Russian is worse than one not in Russian at all: the reader
        meets two languages in one conversation and neither is the one they chose.
        """
        if not self.turns:
            return set()
        codes = set(self.turns[0].said)
        for turn in self.turns[1:]:
            codes &= set(turn.said)
        return {code for code in codes if all(turn.said.get(code) for turn in self.turns)}

    @property
    def words(self) -> int:
        return sum(len(turn.text.split()) for turn in self.turns)

    @property
    def voiced(self) -> bool:
        """Whether every line can be played. Partly-voiced is not voiced."""
        return bool(self.turns) and all(turn.voiced for turn in self.turns)
