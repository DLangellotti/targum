"""French false friends as a practice (targum-internal#644; design.md §12, "French false
friends are practised as the card says them", 2026-11-17): what a flagged word means here,
against the English word it looks like, offered only to a reader reading into English."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_meetings import text
from test_reading_line import ms
from test_serve import Postbox, call, sign_in

from targum import practices, stages
from targum.models import Segment, SegmentedDocument

served = test_serve.served
postbox = test_serve.postbox


def word(surface: str, lemma: str, pos: str) -> dict[str, Any]:
    return {"surface": surface, "lemma": lemma, "pos": pos, "feats": f"UPOS={pos}"}


def asked(lines: list[tuple[str, list[dict[str, Any]]]]) -> list[tuple[str, str, str]]:
    """Every friend item over a text of these lines, as (word, right, wrong)."""
    segments, tokens = [], {}
    for n, (line, words) in enumerate(lines):
        sid = f"s{n}"
        segments.append(Segment(id=sid, block_id="b0", block_index=0, index=n, text=line))
        placed, at = [], 0
        for one in words:
            start = line.index(one["surface"], at)
            placed.append({"start": start, "end": start + len(one["surface"]), **one})
            at = start + len(one["surface"])
        tokens[sid] = placed
    segmented = SegmentedDocument(
        document_hash="t", language="fr", segmenter="t/1", segments=segments
    )
    found = practices.friend_candidates(segmented, tokens, {})
    out = []
    for c in (one for section in found.values() for one in section):
        line = next(s.text for s in segments if s.id == c.segment)
        out.append((line[c.start : c.end], practices.said("friends", c.answer, "en"),
                    practices.said("friends", c.contrast, "en")))  # fmt: skip
    return out


def test_false_friends_are_registered() -> None:
    assert stages._practices("fr")["false friends"] is True
    assert practices.KEYS["false friends"] == "friends"
    assert practices.SPOTS["friends"] == "false friends"
    assert practices.REGISTERED["fr"]["false friends"].kind == "choice"


def test_a_word_the_card_flags_is_asked_what_it_means_against_its_look_alike() -> None:
    line = "Il travaille actuellement à la librairie."
    words = [word("travaille", "travailler", "VERB"), word("actuellement", "actuellement", "ADV"),
             word("librairie", "librairie", "NOUN")]  # fmt: skip
    assert asked([(line, words)]) == [
        ("actuellement", "currently, at present", "actually"),
        ("librairie", "bookshop", "library"),
    ]


def test_a_gated_word_is_asked_only_where_every_use_in_the_text_passes() -> None:
    """*matériel* is said only as a noun, and only where every use in the text is one:
    the card gathers uses over its page, and the practice over the text, so it never says
    more than the card."""
    noun = ("Le matériel est prêt.", [word("matériel", "matériel", "NOUN")])
    adjective = ("Un dommage matériel.", [word("matériel", "matériel", "ADJ")])
    assert asked([noun]) == [("matériel", "equipment, gear", "material")]
    assert asked([noun, adjective]) == []
    # *assister* only before à.
    before = (
        "Il va assister à la fête.",
        [word("assister", "assister", "VERB"), word("à", "à", "ADP")],
    )
    other = (
        "Il faut assister le chef.",
        [word("assister", "assister", "VERB"), word("le", "le", "DET")],
    )
    assert asked([before])[0][1] == "(assister à) to attend, to witness"
    assert asked([before, other]) == []


def test_nothing_is_asked_with_the_list_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_FALSE_FRIENDS", "0")
    line = "Il travaille actuellement."
    assert asked([(line, [word("actuellement", "actuellement", "ADV")])]) == []


@pytest.mark.parametrize("ui", ["en", "ru"])
def test_the_answers_are_english_and_the_rule_names_both(ui: str) -> None:
    code = "actuellement\tactually\tcurrently, at present"
    swapped = "actuellement\tcurrently, at present\tactually"
    assert practices.said("friends", code, ui) == "currently, at present"
    assert practices.said("friends", swapped, ui) == "actually"
    told = practices.rule("friends", code, ui)
    assert "actuellement" in told and "actually" in told and "currently, at present" in told
    assert "{" not in told


def _friends(name: str) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (f"Il travaille actuellement chez {name}.", [word("actuellement", "actuellement", "ADV")]),
        (f"La librairie de {name} ferme.", [word("librairie", "librairie", "NOUN")]),
        (f"Elle va éventuellement venir chez {name}.",
         [word("éventuellement", "éventuellement", "ADV")]),
        (f"Il veut achever son livre chez {name}.", [word("achever", "achever", "VERB")]),
    ]  # fmt: skip


def _sync(port: int, token: str, out: Path, postbox: Postbox, *, english: bool = True) -> str:
    """Two texts of false friends, finished; each with an English translation, as a text
    built into English has, unless `english` is False."""
    for name in ("un", "deux"):
        lines = _friends(name)
        translation = {f"s1-{n}": f"(English of line {n})" for n in range(len(lines))}
        text(out / "shared" / name, {1: lines}, language="fr", content_hash=name,
             translation=translation if english else None)  # fmt: skip
    cookie = sign_in(port, postbox)
    sections = [
        {"hash": name, "section": "1", "at": ms(2026, 11), "seen": ms(2026, 11)}
        for name in ("un", "deux")
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"sections": sections}, cookie=cookie
    )
    assert status == 200, answer
    return cookie


def test_false_friends_are_offered_reading_into_english(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    cookie = _sync(port, token, out, postbox)
    status, said, _ = call(
        port, "GET", f"/account/practice?language=fr&into=en&spot=friends&k={token}", cookie=cookie
    )
    assert status == 200, said
    spot = {one["key"]: one for one in said["spots"]}["friends"]
    assert spot["ready"] and "note" not in spot
    items = said["round"]["items"]
    assert said["round"]["spot"] == "friends" and len(items) == practices.ROUND + 1
    for item in items:
        assert item["ask"] == "What does it mean here?"
        assert item["options"][item["answer"]] == item["said"]
        assert item["line"][item["start"] : item["end"]] == item["word"]
        assert "looks like the English" in item["rule"]


def test_each_text_is_judged_by_the_language_it_is_read_into(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """qa on #1295: not the Grammar tab's language but each text's own. A reader whose
    page is Russian reads these texts in English, the only translation they have, so the
    card says their false friends and the practice asks them."""
    port, token, out = served
    cookie = _sync(port, token, out, postbox)
    status, said, _ = call(
        port, "GET", f"/account/practice?language=fr&into=ru&spot=friends&k={token}", cookie=cookie
    )
    assert status == 200, said
    spot = {one["key"]: one for one in said["spots"]}["friends"]
    assert spot["ready"] and "note" not in spot
    assert said["round"]["spot"] == "friends"


def test_a_reader_not_reading_into_english_is_told_why_and_asked_nothing(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The look-alikes are English words, so the card says them only beside English, and
    a text not read into English asks none. The Russian of the line waits for David's
    pick."""
    port, token, out = served
    cookie = _sync(port, token, out, postbox, english=False)
    status, said, _ = call(
        port, "GET", f"/account/practice?language=fr&into=ru&spot=friends&k={token}", cookie=cookie
    )
    assert status == 200, said
    spot = {one["key"]: one for one in said["spots"]}["friends"]
    assert not spot["ready"] and spot["note"]
    assert said["round"] is None or said["round"]["spot"] != "friends"


def test_the_switch_off_takes_the_spot_away_from_texts_already_counted(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """qa on #1295: a text counted while the list was on keeps its friends in practice.json;
    with the switch off the page neither lists the spot nor asks it."""
    port, token, out = served
    cookie = _sync(port, token, out, postbox)
    path = f"/account/practice?language=fr&into=en&spot=friends&k={token}"
    status, said, _ = call(port, "GET", path, cookie=cookie)
    assert "friends" in {one["key"] for one in said["spots"]}
    assert any(
        "friends" in (out / "shared" / n / practices.CACHE).read_text() for n in ("un", "deux")
    )
    monkeypatch.setenv("TARGUM_FALSE_FRIENDS", "0")
    status, said, _ = call(port, "GET", path, cookie=cookie)
    assert status == 200, said
    assert "friends" not in {one["key"] for one in said["spots"]}
    assert said["round"] is None or said["round"]["spot"] != "friends"
