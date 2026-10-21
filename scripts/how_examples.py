"""Copy the examples on /how out of real builds (targum-internal#401).

/how shows each hard part of Hebrew solved, and the rule is that every example is what
targum made, never a mock. So the examples are not typed into the template: this script
reads them out of build folders — the segments, the pointing, the annotation, the
glossary, the translation and the timings a reader is drawn from — and writes
`src/targum/how.json`, which the page renders and which ships with the package.

The picks are named below by build folder and segment id, and each was read
before it was named: a pick is a sentence the pipeline got right, which is the page's
whole claim. Nothing here spends: the one stage it runs itself is the Aramaic word list,
which is a table lookup.

Run from the main checkout, where `targum-out/` holds the builds:

    uv run python scripts/how_examples.py [--out targum-out]

It refuses to write if a pick has moved — a rebuilt folder whose segment id or word no
longer matches — rather than quietly showing something nobody read.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from targum.annotate import aramaic  # noqa: E402
from targum.vocalize.base import strip_taamim  # noqa: E402

OUT = ROOT / "src" / "targum" / "how.json"

#: The punctuation the transcript refiner may add (`transcribe.refine.punctuate.MARKS`).
#: Taking it off again gives back the run of words the transcriber heard, letter for
#: letter: the refiner keeps a mark only where the heard word stands unchanged around it.
HEARD_MARKS = re.compile(r"[.,?!;:…()–—]")

WEEK_40 = "weekly/weekly-2026-w40-aleph-he"

#: Where an example from targum's own weekly news is from; the page says it in its
#: language. Anything else is a reference, said as it is written.
WEEKLY = "weekly"


def load(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text(encoding="utf-8"))


class Build:
    """One build folder, read the way the reader reads it."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.segments = {s["id"]: s for s in load(folder, "segments.json")["segments"]}
        self.pointing: dict[str, str] = {}
        if (folder / "vocalization.json").exists():
            self.pointing = load(folder, "vocalization.json")["segments"]
        self.tokens: dict[str, list[dict[str, Any]]] = {}
        if (folder / "annotation.json").exists():
            self.tokens = load(folder, "annotation.json")["tokens"]
        self.glossary: dict[str, str] = {}
        if (folder / "glossary.en.json").exists():
            self.glossary = load(folder, "glossary.en.json")["entries"]
        self.english: dict[str, str] = {}
        for path in sorted((folder / "translations").glob("*.en.json")):
            self.english = load(path.parent, path.name)["segments"]
            break

    def text(self, sid: str) -> str:
        if sid not in self.segments:
            raise SystemExit(f"{self.folder}: no segment {sid}; the pick has moved")
        return str(self.segments[sid]["text"])

    def pointed(self, sid: str) -> str:
        """The sentence as the reader shows it: the source's own points where it has them
        (the Tanakh), else the pointing targum added. Chanting marks off, as the reader
        starts."""
        return strip_taamim(self.pointing.get(sid) or self.text(sid))

    def token(self, sid: str, surface: str) -> dict[str, Any]:
        for token in self.tokens.get(sid, []):
            if aramaic.bare(token["surface"]) == surface:
                return token
        raise SystemExit(f"{self.folder}: {surface} is not a word of {sid}")

    def split(self, sid: str, surface: str) -> dict[str, str]:
        """The pointed sentence in three pieces around one word, by word count: pointing
        adds marks and never a space, so the nth word of one is the nth of the other."""
        token = self.token(sid, surface)
        plain = self.text(sid)
        # Words and what stands between them, a maqaf included: in the Tanakh את־ירד is
        # two words joined, and the card is about the second.
        pieces = re.split(r"(\s+|־)", self.pointed(sid))
        words = range(0, len(pieces), 2)
        before = plain[: token["start"]].strip()
        guess = len(re.split(r"\s+|־", before)) if before else 0
        matches = [i for i in words if aramaic.key(surface) == aramaic.key(pieces[i])]
        if not matches:
            raise SystemExit(f"{self.folder}: {surface} is not a word of {sid}")
        at = min(matches, key=lambda i: abs(i // 2 - guess))
        word = pieces[at]
        # Punctuation after the word stays with the sentence, not on the card.
        tail = re.search(r"[.,?!:;׃\"]+$", word)
        trailing = tail.group(0) if tail else ""
        return {
            "before": "".join(pieces[:at]),
            "word": word[: len(word) - len(trailing)],
            "after": trailing + "".join(pieces[at + 1 :]),
        }

    def gloss(self, token: dict[str, Any]) -> str:
        lemma = token["lemma"]
        if token.get("pos") == "VERB" and f"{lemma} (verb)" in self.glossary:
            return self.glossary[f"{lemma} (verb)"]
        return self.glossary.get(lemma, "")


def kind(token: dict[str, Any]) -> str:
    """What the card says a word is, in a learner's words rather than a tagger's."""
    pos = token.get("pos")
    feats = token.get("feats") or ""
    if pos == "PROPN":
        return "name"
    if pos == "VERB":
        return "verb, past" if "Tense=Past" in feats else "verb"
    return {"NOUN": "noun", "ADJ": "adjective"}.get(pos or "", "")


def vowels(out: Path) -> dict[str, Any]:
    week = Build(out / "weekly/weekly-2026-w35-aleph-he")
    ids = [s for s in week.segments if week.segments[s]["block_id"] == "b0021"]
    return {
        "where": "weekly",
        "plain": " ".join(week.text(i) for i in ids),
        "pointed": " ".join(week.pointed(i) for i in ids),
        "english": " ".join(week.english[i] for i in ids),
    }


def homographs(out: Path) -> list[list[dict[str, Any]]]:
    week = Build(out / WEEK_40)
    genesis = Build(out / "library/בראשית-he")

    def card(build: Build, sid: str, surface: str, where: str, meaning: str = "") -> dict:
        token = build.token(sid, surface)
        return {
            "letters": surface,
            "kind": kind(token),
            "meaning": meaning or build.gloss(token),
            "sentence": build.split(sid, surface),
            "english": build.english.get(sid, ""),
            "where": where,
        }

    return [
        [
            card(week, "0001.000-7f2c97", "דיווח", WEEKLY),
            card(week, "0004.000-c62bd2", "דיווח", WEEKLY),
        ],
        [
            card(week, "0008.002-c5605b", "ירד", WEEKLY),
            # A name has no glossary line; the translation names him.
            card(genesis, "0125.000-ad87b4", "ירד", "Genesis 5:15", meaning="Yered"),
        ],
    ]


def prefixes(out: Path) -> list[dict[str, Any]]:
    picks = [
        ("weekly/weekly-2026-w39-gimel-he", "0025.001-94bac7", "כשהמכשיר"),
        ("weekly/weekly-2026-w35-gimel-he", "0012.002-4e5fdd", "ובמוסדותיה"),
        ("weekly/weekly-2026-w35-aleph-he", "0012.001-da919e", "מהמפגינים"),
    ]
    found = []
    for folder, sid, surface in picks:
        build = Build(out / folder)
        token = build.token(sid, surface)
        built = token.get("built") or ""
        pieces = [piece.strip() for piece in built.split("+")]
        parts = []
        for piece in pieces:
            letters, _, means = piece.partition(" ")
            if not re.fullmatch(r"[א-ת]", letters):
                continue
            parts.append({"letters": letters, "means": means})
        stem = next(p for p in pieces if re.match(r"[א-ת]{2,}", p))
        found.append(
            {
                "surface": surface,
                "word": build.split(sid, surface)["word"].strip(",."),
                "parts": parts,
                "stem": stem.split(" ")[0],
                "suffix": "with a pronoun on the end" in built,
                "lemma": token["lemma"],
                "meaning": build.gloss(token),
            }
        )
    return found


def roots(out: Path) -> dict[str, Any]:
    genesis = Build(out / "library/בראשית-he")
    exodus = Build(out / "library/שמות-he")
    w35 = Build(out / "weekly/weekly-2026-w35-bet-he")
    w40 = Build(out / WEEK_40)

    def use(
        build: Build, sid: str, surface: str, where: str, english_to: str = "", cut: int = 0
    ) -> dict:
        token = build.token(sid, surface)
        if token.get("root") != "עלה":
            raise SystemExit(f"{build.folder}: {surface} is filed under {token.get('root')}")
        english = build.english.get(sid, "")
        if english_to:
            english = english[: english.index(english_to) + len(english_to)] + " …"
        sentence = build.split(sid, surface)
        if cut:
            # A long verse, quoted to where its English is quoted to.
            sentence["after"] = " ".join(sentence["after"].split(" ")[: cut + 1]) + " …"
        return {
            "binyan": token["binyan"],
            "sentence": sentence,
            "english": english,
            "where": where,
        }

    # The meaning of each pattern is the page's own line, not a glossary's: the glossary
    # files a word, and here it is the pattern that is being explained.
    rows = [
        (
            "פעל",
            "פָּעַל",
            "go up",
            [
                use(genesis, "0038.000-ff3f14", "יעלה", "Genesis 2:6"),
                use(w35, "0024.003-1084df", "עלתה", WEEKLY),
            ],
        ),
        (
            "הפעיל",
            "הִפְעִיל",
            "bring up, raise",
            [
                use(exodus, "0057.000-229a45", "ולהעלתו", "Exodus 3:8", "from that land", cut=2),
                use(w40, "0020.003-9c3b40", "מעלה", WEEKLY),
            ],
        ),
        (
            "נפעל",
            "נִפְעַל",
            "be lifted",
            [
                use(exodus, "1247.000-15b73e", "ובהעלות", "Exodus 40:36"),
            ],
        ),
    ]
    for binyan, _, _, uses in rows:
        for found in uses:
            if found["binyan"] != binyan:
                raise SystemExit(f"{found['where']} is {found['binyan']}, not {binyan}")
    return {
        "root": "ע־ל־ה",
        "rows": [
            {"pattern": pattern, "meaning": meaning, "uses": uses}
            for _, pattern, meaning, uses in rows
        ],
    }


def speech(out: Path) -> dict[str, Any]:
    folder = out / "demos/olim/shelf/p1/team-sync-he"
    build = Build(folder)
    words = load(folder, "audio.json")["parts"][0]["words"]
    ids = ["10003.000-ab80db", "10003.001-6c2605", "10003.002-a90130"]
    sentences = []
    for sid in ids:
        text = build.text(sid)
        timed = [
            {"word": text[int(start) : int(end)], "at": round(begin, 2)}
            for start, end, begin, _ in words[sid]
        ]
        if len(timed) != len(text.split()):
            raise SystemExit(f"{folder}: {sid} has a word with no time; pick another")
        sentences.append({"words": timed, "english": build.english.get(sid, "")})
    heard = " ".join(HEARD_MARKS.sub("", build.text(sid)) for sid in ids)
    return {"heard": " ".join(heard.split()), "sentences": sentences}


def poster(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as image:
        image.thumbnail((216, 384))
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "WEBP", quality=62)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def media(out: Path) -> dict[str, Any]:
    reel_folder = out / "p3/local/0zihpfw-4ey-he"
    reel = Build(reel_folder)
    frame = load(reel_folder, "audio.json")["parts"][0]["frame"]
    lines = ["10003.000-d07d7b", "10005.000-095e94"]
    chat = Build(out / "demos/olim/shelf/p1/אבי-·-ועד-הבית,-רינה-קומה-3,-משה-he")
    document = load(chat.folder, "document.json")
    turns = []
    for block in document["blocks"][:3]:
        said = [s["id"] for s in chat.segments.values() if s["block_id"] == block["id"]]
        turns.append(
            {
                "speaker": block["speaker"],
                # As it was typed: a chat is read unpointed, as it was sent.
                "text": " ".join(chat.text(s) for s in said),
                "english": " ".join(chat.english.get(s, "") for s in said),
            }
        )
    return {
        "reel": {
            "author": "Vegan Friendly",
            "home": "https://www.youtube.com/shorts/0zIhpFW_4EY",
            "tall": frame[1] > frame[0],
            "poster": poster(reel_folder / "poster.jpg"),
            "lines": [
                {"pointed": reel.pointed(sid), "english": reel.english[sid]} for sid in lines
            ],
        },
        "chat": {"turns": turns},
    }


def onkelos() -> dict[str, Any]:
    fixtures = ROOT / "tests" / "fixtures" / "sefaria"
    verse = json.loads((fixtures / "onkelos-genesis-1-2.arc.json").read_text("utf-8"))
    hebrew = json.loads((fixtures / "genesis-1-2.he.json").read_text("utf-8"))
    targum = verse["versions"][0]["text"][0][0]
    torah = strip_taamim(hebrew["versions"][0]["text"][0][0])
    ref = "Onkelos Genesis 1:1"
    segment = aramaic.Segment(
        id="v", block_id="b", block_index=0, index=0, text=aramaic.bare(targum), ref=ref
    )
    pointed = targum.split()
    words = []
    for token, form in zip(aramaic.tokens(segment), pointed, strict=True):
        meaning = aramaic.sense(token.lexeme)
        words.append(
            {
                "form": form,
                "headword": token.headword or "",
                "built": token.built or "",
                "meaning": meaning,
            }
        )
    return {"where": "Genesis 1:1", "torah": torah, "onkelos": targum, "words": words}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "targum-out")
    args = parser.parse_args()
    out: Path = args.out
    examples = {
        "vowels": vowels(out),
        "homographs": homographs(out),
        "prefixes": prefixes(out),
        "roots": roots(out),
        "speech": speech(out),
        "media": media(out),
        "aramaic": onkelos(),
    }
    OUT.write_text(json.dumps(examples, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
