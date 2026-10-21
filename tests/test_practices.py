"""A practice for each hard spot (targum-internal#440; design.md §12, "A practice for every
hard spot", 2026-10-13): what each spot asks of a stored word, the encounter ledger, the
band a round is held in, the schedule, and `/account/practice` end to end."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_meetings import text
from test_reading_line import ms
from test_serve import Postbox, call, sign_in

from targum import practices, stages
from targum.practices import Candidate, State

served = test_serve.served
postbox = test_serve.postbox


def verb(surface: str, lemma: str, feats: str, binyan: str = "פעל") -> dict[str, Any]:
    return {"surface": surface, "lemma": lemma, "pos": "VERB", "feats": feats, "binyan": binyan}


def spots_of(token: dict[str, Any]) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {}
    for one in practices.candidates({"start": 0, "end": 1, **token}, "s"):
        out.setdefault(one.spot, []).append(one)
    return out


def test_every_hebrew_spot_has_a_registered_practice() -> None:
    """The register is what the stage standard reads; governed prepositions are
    practised by their lens (design.md §12, "Lenses wait for a second read")."""
    names = [spot.name for spot in stages.HARD_SPOTS["he"]]
    registered = practices.REGISTERED["he"]
    assert set(registered) == set(names)
    assert registered["governed prepositions and et"].kind == "lens"
    known = stages.facts("he")
    assert all(known.practices.values()), known.practices


def test_the_lens_spot_is_counted_from_the_syntax() -> None:
    stored = [
        {"start": 0, "end": 4, "surface": "דיבר", "lemma": "דיבר", "band": 0, "pos": "VERB",
         "syntax": {"head": -1, "relation": "root", "prefixes": [], "lead": 0}},
        {"start": 5, "end": 7, "surface": "עם", "lemma": "עם", "band": 0, "pos": "ADP",
         "syntax": {"head": 2, "relation": "case", "prefixes": [], "lead": 0}},
        {"start": 8, "end": 13, "surface": "המנהל", "lemma": "מנהל", "band": 0, "pos": "NOUN",
         "syntax": {"head": 0, "relation": "obl", "prefixes": ["DET"], "lead": 1}},
    ]  # fmt: skip
    (one,) = practices._governed(stored, "s")
    assert (one.spot, one.start, one.end, one.answer) == ("governed", 0, 4, "עם")


def test_a_biblical_text_offers_no_governed_preposition(tmp_path: Path) -> None:
    """targum-internal#454: the spot is declared out of Biblical text, so a verse whose
    few words DICTA's fallback parsed offers nothing to practise; the same line in a
    modern text does."""
    import json

    # The same three words as the lens test above, band and all: `text` places each by
    # its surface, and `_governed` validates them as tokens.
    words = [
        {"surface": "דיבר", "lemma": "דיבר", "band": 0, "pos": "VERB",
         "syntax": {"head": -1, "relation": "root", "prefixes": [], "lead": 0}},
        {"surface": "עם", "lemma": "עם", "band": 0, "pos": "ADP",
         "syntax": {"head": 2, "relation": "case", "prefixes": [], "lead": 0}},
        {"surface": "המנהל", "lemma": "מנהל", "band": 0, "pos": "NOUN",
         "syntax": {"head": 0, "relation": "obl", "prefixes": ["DET"], "lead": 1}},
    ]  # fmt: skip
    folder = text(tmp_path / "t", {1: [("דיבר עם המנהל", words)]})
    modern = practices.count_text(folder)
    assert modern is not None
    offered = [c for c in modern.by_section[1] if c.spot == "governed"]
    assert [(c.start, c.end, c.answer) for c in offered] == [(0, 4, "עם")], modern
    said = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    said["source"] = "sefaria:Genesis 1"
    (folder / "document.json").write_text(json.dumps(said), encoding="utf-8")
    biblical = practices.count_text(folder)
    assert biblical is not None
    assert not [c for c in biblical.by_section[1] if c.spot == "governed"]


def test_a_verb_asks_its_binyan_and_its_tense_and_person() -> None:
    found = spots_of(verb("כתבתי", "כתב", "UPOS=VERB|Tense=Past|Person=1|Number=Sing"))
    binyan = {(c.answer, c.contrast, c.hard) for c in found["binyan"]}
    assert binyan == {("פעל", "פיעל", True), ("פעל", "התפעל", False)}
    tense = {(c.contrast, c.hard) for c in found["tense"]}
    assert ("Tense=Past|Person=3|Number=Sing", True) in tense
    assert ("Tense=Fut|Person=1|Number=Sing", False) in tense
    assert all(c.answer == "Tense=Past|Person=1|Number=Sing" for c in found["tense"])


def test_agreement_is_asked_of_adjectives_and_participles() -> None:
    found = spots_of(
        {"surface": "גדולות", "lemma": "גדול", "pos": "ADJ", "feats": "Gender=Fem|Number=Plur"}
    )
    assert {(c.contrast, c.hard) for c in found["agreement"]} == {
        ("Gender=Masc|Number=Plur", True),
        ("Gender=Fem|Number=Sing", False),
    }
    past = spots_of(verb("כתבה", "כתב", "Tense=Past|Person=3|Gender=Fem|Number=Sing"))
    assert "agreement" not in past, "a past verb agrees, but that is tense and person's card"


def test_the_construct_state_is_asked_both_ways() -> None:
    bound = spots_of(
        {
            "surface": "בית",
            "lemma": "בית",
            "pos": "NOUN",
            "feats": "Gender=Masc|Number=Sing|Definite=Cons",
        }
    )
    assert [(c.answer, c.contrast, c.hard) for c in bound["construct"]] == [("Cons", "Free", True)]
    free = spots_of(
        {
            "surface": "הבתים",
            "lemma": "בית",
            "pos": "NOUN",
            "feats": "Gender=Masc|Number=Plur|Definite=Def",
        }
    )
    assert [(c.answer, c.hard) for c in free["construct"]] == [("Free", False)]
    assert "construct" not in spots_of(
        {"surface": "בית", "lemma": "בית", "pos": "NOUN", "feats": ""}
    )


def test_stress_is_asked_only_where_the_text_placed_it() -> None:
    """A guessed stress is never a right answer (known issues 2.2); a placed one is."""
    guessed = spots_of({"surface": "דוד", "lemma": "דוד", "pos": "PROPN", "ipa": "davˈid"})
    assert "stress" not in guessed
    placed = spots_of({"surface": "דָּוִ֖יד", "lemma": "דוד", "pos": "PROPN", "ipa": "davˈid"})
    (one,) = placed["stress"]
    assert (one.answer, one.contrast) == ("davˈid", "ˈdavid")


def test_a_reading_is_said_as_the_card_says_it() -> None:
    assert practices.plainly("hithaˈleχ") == "hit-ha-lékh"
    assert practices.plainly("davˈid", "ru") == "да-ви́д"
    assert practices.plainly("ˈkol") == "kol"


def test_answers_are_said_in_words() -> None:
    assert practices.said("tense", "Tense=Past|Person=1|Number=Sing", "en") == "past · I"
    assert (
        practices.said("tense", "Tense=Fut|Person=3|Gender=Fem|Number=Sing", "en") == "future · she"
    )
    assert practices.said("agreement", "Gender=Fem|Number=Plur", "en") == "feminine · plural"
    assert practices.said("construct", "Cons", "en").startswith("bound")
    assert practices.said("stress", "davˈid", "en") == "da-víd"
    assert practices.said("homograph", "ספר", "en", {"ספר": "סֵפֶר"}) == "סֵפֶר"


def vav(pointed: str, feats: str) -> list[Candidate]:
    token = {"start": 0, "end": len(pointed), "pos": "VERB", "feats": feats}
    return list(practices.vav_candidates(token, pointed, "s"))


def test_the_vav_consecutive_is_asked_past_or_future_against_the_plain_vav() -> None:
    """targum-internal#449. ויאמר in a finished Biblical line is past, the easy kind; a
    plain vav on a future form (Open Scriptures' `Vqi`) stays future, the hard kind, and
    each is the other's contrast."""
    said = "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin|Vav=Cons"
    ((one,),) = [vav("וַיֹּ֥אמֶר", said)]
    assert (one.spot, one.answer, one.contrast, one.hard) == ("vav", "Past", "Fut", False)
    # The first person, whose א cannot double: the vav takes a qamats.
    assert [c.answer for c in vav("וָאֹמַר", "UPOS=VERB|Tense=Past")] == ["Past"]
    plain = "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Fut|VerbForm=Fin"
    ((two,),) = [vav("וְיֹאמַ֣ר", plain)]
    assert (two.answer, two.contrast, two.hard) == ("Fut", "Past", True)
    # A shureq is a plain vav too.
    assert [c.answer for c in vav("וּתְדַבֵּר", plain)] == ["Fut"]
    # A plain vav on a past form is not this spot, nor is a word with no vav, nor a noun.
    assert vav("וְאָמַרְתָּ", "UPOS=VERB|Tense=Past") == []
    assert vav("יֹאמַר", plain) == []
    noun = {"start": 0, "end": 5, "pos": "NOUN", "feats": ""}
    assert list(practices.vav_candidates(noun, "וָאָרֶץ", "s")) == []
    assert practices.said("vav", "Past", "en") == "past"
    assert practices.said("vav", "Fut", "en") == "future"
    assert "doubled letter" in practices.rule("vav", "Past", "en")
    assert "plain" in practices.rule("vav", "Fut", "en")
    assert practices.REGISTERED["he"]["the vav-consecutive"].kind == "choice"
    assert practices.KEYS["the vav-consecutive"] == "vav"


def test_the_vav_consecutive_is_read_off_the_pointed_line_in_scripture_alone(
    tmp_path: Path,
) -> None:
    """The stored surface of a verse is bare, so the line's own points decide; and a text
    that is not scripture asks nothing, because the spot is declared Biblical only."""
    import json

    line = "וַיֹּ֥אמֶר אֱלֹהִ֖ים"
    token = {"surface": "וַיֹּ֥אמֶר", "lemma": "אמר", "pos": "VERB", "feats": "Tense=Past"}
    folder = text(tmp_path / "gen", {1: [(line, [token])]})
    modern = practices.count_text(folder)
    assert modern is not None
    assert not [c for c in modern.by_section[1] if c.spot == "vav"]
    said = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    said["source"] = "sefaria:Genesis 1"
    (folder / "document.json").write_text(json.dumps(said), encoding="utf-8")
    found = practices.count_text(folder)
    assert found is not None
    ((one,),) = [[c for c in found.by_section[1] if c.spot == "vav"]]
    assert (one.answer, one.start, one.end) == ("Past", 0, len("וַיֹּ֥אמֶר"))


def test_a_pronoun_suffix_is_asked_whose_against_its_look_alike() -> None:
    """targum-internal#450. לפניהם is "before them"; the look-alike is the hard kind (ם
    against ן) and another person the easy one, each said in the card's own words."""
    token = {
        "start": 0,
        "end": 6,
        "surface": "לפניהם",
        "lemma": "לפני",
        "pos": "ADP",
        "built": "לפניהם + with a pronoun on the end",
    }
    hard, easy = practices.suffix_candidates(token, "לפניהם", "s")
    assert (hard.spot, hard.hard, easy.hard) == ("suffix", True, False)
    assert hard.answer == easy.answer == "3mp:before them"
    assert hard.contrast == "3fp:before them (f.)"
    assert easy.contrast == "3ms:before him"
    assert practices.said("suffix", hard.answer, "en") == "before them"
    assert "their, or them" in practices.rule("suffix", hard.answer, "en")
    noun = {
        **token,
        "surface": "ספרו",
        "lemma": "ספר",
        "pos": "NOUN",
        "built": "ספרו + with a pronoun on the end",
    }
    (one, _) = practices.suffix_candidates(noun, "ספרו", "s")
    assert (one.answer, one.contrast) == ("3ms:his", "1cs:my")
    # A word with no pronoun on the end asks nothing.
    bare = {**token, "built": None}
    assert list(practices.suffix_candidates(bare, "לפני", "s")) == []
    assert practices.REGISTERED["he"]["pronoun suffixes"].kind == "choice"
    assert practices.KEYS["pronoun suffixes"] == "suffix"


def test_a_pronoun_suffix_is_asked_in_both_registers(tmp_path: Path) -> None:
    """Claimed in modern and Biblical text alike: the same line asks it either way."""
    import json

    line = "וַיִּתֵּן לִפְנֵיהֶם"
    token = {"surface": "לפניהם", "lemma": "פנים", "pos": "NOUN", "built": "ל + פני + הם"}
    folder = text(tmp_path / "gen", {1: [(line, [{**token, "surface": "לִפְנֵיהֶם"}])]})
    modern = practices.count_text(folder)
    assert modern is not None
    assert [c.answer for c in modern.by_section[1] if c.spot == "suffix"] == [
        "3mp:before them",
        "3mp:before them",
    ]
    said = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    said["source"] = "sefaria:Genesis 18"
    (folder / "document.json").write_text(json.dumps(said), encoding="utf-8")
    (folder / "practice.json").unlink(missing_ok=True)
    found = practices.count_text(folder)
    assert found is not None
    assert len([c for c in found.by_section[1] if c.spot == "suffix"]) == 2


def test_the_ledger_counts_a_line_once_and_needs_two_texts() -> None:
    def met(document: str, segment: str) -> practices.Met:
        return practices.Met(
            Candidate("tense", segment, 0, 1, "a", "b", True), document, Path("."), 1
        )

    six_in_one = [met("one", f"s{n}") for n in range(6)] + [met("one", "s0")]
    count = practices.ledger(six_in_one)
    assert count.encounters("tense") == 6 and count.texts("tense") == 1
    assert not count.ready("tense"), "six lines in one text is not yet enough"
    count = practices.ledger([*six_in_one, met("two", "s0")])
    assert count.ready("tense")


def _found(n: int) -> list[practices.Met]:
    return [
        practices.Met(Candidate("tense", f"s{k}", 0, 1, "a", "b", k % 2 == 0), "doc", Path("."), 1)
        for k in range(n)
    ]


@pytest.mark.parametrize(
    ("history", "hard"),
    [("1" * 20, True), ("0" * 10 + "1" * 10, False), ("1" * 14 + "0" * 6, None)],
)
def test_the_round_holds_the_band(history: str, hard: bool | None) -> None:
    """Above 85% the round draws hard items, below 60% easy ones, inside both."""
    state = State(history=history)
    picked = practices.choose(_found(40), state, seed=1)
    assert len(picked) == practices.ROUND + 1
    kinds = {one.candidate.hard for one in picked}
    assert kinds == ({hard} if hard is not None else {True, False})


def test_a_line_is_never_asked_twice() -> None:
    found = _found(8)
    state = State(seen=[practices.line_key("doc", f"s{k}") for k in range(5)])
    picked = practices.choose(found, state, seed=2)
    assert {one.candidate.segment for one in picked} == {"s5", "s6", "s7"}


def test_a_round_moves_the_spot_up_or_down_the_ramp() -> None:
    now = 1_000_000.0
    up = practices.finished_round(State(step=1), right=4, asked=5, now=now)
    assert up.step == 2 and up.due == int(now) + 7 * 86400
    down = practices.finished_round(State(step=2), right=1, asked=5, now=now)
    assert down.step == 1
    floor = practices.finished_round(State(step=0), right=0, asked=5, now=now)
    assert floor.step == 0 and floor.due == int(now) + 86400
    state = practices.answered(State(history="1" * 20), False, "doc:s1")
    assert len(state.history) == practices.WINDOW and state.history.endswith("0")
    assert state.seen == ["doc:s1"]


# -- /account/practice, end to end ------------------------------------------------------


def _verbs(name: str, n: int) -> list[tuple[str, list[dict[str, Any]]]]:
    lines = []
    for k in range(n):
        person = "1" if k % 2 else "3"
        lines.append(
            (
                f"כתב{name}{k} מכתב",
                [
                    verb(
                        f"כתב{name}{k}",
                        "כתב",
                        f"Tense=Past|Person={person}|Gender=Masc|Number=Sing",
                    )
                ],
            )
        )
    return lines


def test_the_practice_page_is_nobodys_business_signed_out(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/account/practice?language=he&k={token}")
    assert status == 401 and said == {"signedIn": False}


def test_a_spot_met_often_enough_is_offered_and_an_answer_is_kept(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    for name in ("one", "two"):
        text(out / "shared" / name, {1: _verbs(name, 4)}, content_hash=name)
    cookie = sign_in(port, postbox)
    sections = [
        {"hash": name, "section": "1", "at": ms(2026, 10), "seen": ms(2026, 10)}
        for name in ("one", "two")
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/practice?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    spots = {spot["key"]: spot for spot in said["spots"]}
    assert spots["tense"]["encounters"] == 8 and spots["tense"]["texts"] == 2
    assert spots["tense"]["ready"] and not spots["construct"]["ready"]
    round_ = said["round"]
    assert round_["spot"] in ("tense", "binyan")
    items = round_["items"]
    assert items and items[0]["example"] and not any(item["example"] for item in items[1:])
    first = items[1]
    assert len(first["options"]) == 2 and first["options"][first["answer"]] == first["said"]
    assert first["line"][first["start"] : first["end"]] == first["word"]
    assert first["rule"]

    status, kept, _ = call(
        port,
        "POST",
        f"/practice?k={token}",
        {"language": "he", "spot": round_["spot"], "key": first["key"], "right": True},
        cookie=cookie,
    )
    assert status == 200 and kept["ok"], kept
    status, kept, _ = call(
        port,
        "POST",
        f"/practice?k={token}",
        {"language": "he", "spot": round_["spot"], "done": [5, 5]},
        cookie=cookie,
    )
    assert kept["step"] == 1 and kept["due"] > 0

    status, again, _ = call(
        port, "GET", f"/account/practice?language=he&spot={round_['spot']}&k={token}", cookie=cookie
    )
    keys = [item["key"] for item in again["round"]["items"]]
    assert first["key"] not in keys, "a line answered is not asked again"

    status, refused, _ = call(
        port, "POST", f"/practice?k={token}", {"language": "he", "spot": "nonsense"}, cookie=cookie
    )
    assert status == 400
