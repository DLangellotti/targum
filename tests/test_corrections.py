"""The correction store, door 1 (targum-internal#164): every human judgement about a
word, kept with provenance. Today the author's hand on a gloss and a grounding at a
reader's tap; the editor's and the reader's doors come later."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import Store
from targum.annotate import gloss as gloss_module
from targum.annotate.gloss import Sense, forget_gloss, gloss_one, set_gloss
from targum.cache import Cache
from targum.cli import app
from targum.serve import grounding_note


def test_a_judgement_is_written_down_with_its_provenance_and_read_back_newest_first(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "words.db")
    assert store.corrections() == []
    first = store.correct(
        "gloss",
        who="author",
        licence="targum",
        term="עם",
        language="he",
        target="en",
        before="people; nation",
        after="with",
        context="הלכתי עם אחי",
        reason="the preposition, not the noun",
    )
    second = store.correct("lemma", who="editor", term="שרוצים", before="רצה", after="רוצה")
    rows = store.corrections()
    assert [row["id"] for row in rows] == [second, first], "newest first"
    assert rows[1]["who"] == "author" and rows[1]["licence"] == "targum"
    assert rows[1]["before"] == "people; nation" and rows[1]["after"] == "with"
    assert rows[1]["context"] == "הלכתי עם אחי" and rows[1]["at"] > 0
    assert [row["stage"] for row in store.corrections(stage="lemma")] == ["lemma"]
    long = store.correct("gloss", who="reader", context="x" * 2000)
    assert len(store.corrections(stage="gloss", limit=1)[0]["context"]) == 500
    assert long > second


def test_the_authors_hand_on_a_gloss_applies_and_returns_what_stood(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    assert forget_gloss("עם", "he", "en", "test", cache=cache) is None, "nothing stood"
    stood = set_gloss("עם", "he", "en", "test", Sense("with"), cache=cache)
    assert stood is None
    key = cache.key("gloss", lemma="עם", source="he", target="en", provider="test")
    kept = cache.get("gloss", key)
    assert kept == {
        "gloss": "with",
        "part_of_speech": "",
        "citation": "",
        "plural": "",
        "grounded": True,
    }, "the author's gloss stands for good: grounded, so no sentence buys it again"
    was = forget_gloss("עם", "he", "en", "test", cache=cache)
    assert was is not None and was.gloss == "with" and was.grounded
    assert cache.get("gloss", key) is None and not cache.drop("gloss", key)


class Provider:
    name = "test"

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    def gloss(
        self,
        lemmas: list[str],
        source: str,
        target: str,
        _on: Any,
        contexts: dict[str, str] | None = None,
    ) -> dict[str, tuple[str, str, str, str]]:
        context = (contexts or {}).get(lemmas[0], "")
        self.asked.append((lemmas[0], context))
        return {lemmas[0]: (("with" if context else "people; nation"), "", "", "")}


def test_a_grounding_tells_the_store_what_stood_and_what_stands(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    provider = Provider()
    told: list[tuple[Sense | None, Sense, str]] = []

    def note(before: Sense | None, after: Sense, context: str) -> None:
        told.append((before, after, context))

    bare = gloss_one("עם", "he", "en", provider, cache=cache, on_grounded=note)  # type: ignore[arg-type]
    assert bare is not None and bare.gloss == "people; nation" and not bare.grounded
    assert told == [], "bought bare: nobody decided anything"
    grounded = gloss_one(
        "עם",
        "he",
        "en",
        provider,
        cache=cache,
        context="הלכתי עם אחי",
        on_grounded=note,  # type: ignore[arg-type]
    )
    assert grounded is not None and grounded.grounded and grounded.gloss == "with"
    assert len(told) == 1
    before, after, context = told[0]
    assert before is not None and before.gloss == "people; nation"
    assert after.gloss == "with" and context == "הלכתי עם אחי"
    again = gloss_one(
        "עם",
        "he",
        "en",
        provider,
        cache=cache,
        context="עם ישראל",
        on_grounded=note,  # type: ignore[arg-type]
    )
    assert again == grounded and len(told) == 1, "grounded stands; nothing is bought or told"


def test_the_readers_grounding_row_names_a_role_and_never_fails_the_lookup(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    note = grounding_note(store, "עם", "he", "en")
    note(Sense("people; nation"), Sense("with", grounded=True), "הלכתי עם אחי")
    (row,) = store.corrections()
    assert row["who"] == "reader" and row["licence"] == ""
    assert row["before"] == "people; nation" and row["after"] == "with"
    assert row["context"] == "הלכתי עם אחי" and row["term"] == "עם"
    grounding_note(None, "עם", "he", "en")(None, Sense("with"), "x"), "no store, no row, no error"
    note(None, Sense("with", grounded=True), "y")
    assert store.corrections()[0]["before"] == "", "a word that had no gloss stood as nothing"


def test_the_command_applies_the_correction_and_keeps_the_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    db = tmp_path / "words.db"
    runner = CliRunner()
    said = runner.invoke(
        app,
        [
            "correct",
            "עם",
            "--meaning",
            "with",
            "--context",
            "הלכתי עם אחי",
            "--reason",
            "preposition",
            "--store",
            str(db),
        ],
    )
    assert said.exit_code == 0, said.output
    assert "Recorded #1" in said.output and "was not glossed" in said.output
    rows = Store(db).corrections()
    assert (
        rows[0]["who"] == "author" and rows[0]["after"] == "with" and rows[0]["licence"] == "targum"
    )

    gone = runner.invoke(app, ["correct", "עם", "--forget", "--store", str(db)])
    assert gone.exit_code == 0, gone.output
    assert "was 'with'" in gone.output and "forgotten" in gone.output
    assert (
        Store(db).corrections()[0]["after"] == "" and Store(db).corrections()[0]["before"] == "with"
    )

    neither = runner.invoke(app, ["correct", "עם", "--store", str(db)])
    assert neither.exit_code != 0
    both = runner.invoke(app, ["correct", "עם", "--meaning", "x", "--forget", "--store", str(db)])
    assert both.exit_code != 0

    listed = runner.invoke(app, ["corrections", "--store", str(db)])
    assert (
        listed.exit_code == 0
        and "#2 gloss author" in listed.output
        and "#1 gloss author" in listed.output
    )
    empty = runner.invoke(app, ["corrections", "--stage", "lemma", "--store", str(db)])
    assert "No corrections yet." in empty.output


# -- the candidate gold set (targum-internal#164, acceptance 4) -------------------------


def _judged(store: Store, who: str, after: str, term: str = "עם", stage: str = "gloss") -> int:
    return store.correct(stage, who=who, term=term, language="he", target="en", after=after)


def test_two_kinds_of_judge_agreeing_is_a_candidate_gold_row(tmp_path: Path) -> None:
    """Acceptance 4: a gold example once a second judge agrees. The author grounded it by
    hand and a reader's tap bought the same sense back — two roles, reached apart."""
    store = Store(tmp_path / "words.db")
    assert store.agreed() == []
    _judged(store, "author", "with")
    _judged(store, "reader", "with")
    found = store.agreed()
    assert len(found) == 1
    row = found[0]
    assert row["term"] == "עם" and row["after"] == "with"
    assert row["judges"] == 2 and row["seen"] == 2
    assert sorted(str(row["roles"]).split(",")) == ["author", "reader"]


def test_one_role_twice_is_one_judge(tmp_path: Path) -> None:
    """`who` is a role and never a person, so two `reader` rows may be one reader twice.
    Counting rows would call that corroboration; counting roles does not. Smaller and
    never wrong — the alternative needs an anonymised judge id the table does not keep."""
    store = Store(tmp_path / "words.db")
    _judged(store, "reader", "with")
    _judged(store, "reader", "with")
    assert store.agreed() == [], "the same role twice is not a second judge"
    _judged(store, "editor", "with")
    assert len(store.agreed()) == 1, "and a different role is"


def test_the_model_is_not_a_judge(tmp_path: Path) -> None:
    """This card is every *human* judgement. A sense the model produced agreeing with a
    person is not two people agreeing."""
    store = Store(tmp_path / "words.db")
    _judged(store, "author", "with")
    _judged(store, "model", "with")
    assert store.agreed() == []


def test_a_deletion_is_not_a_gold_answer(tmp_path: Path) -> None:
    """`after = ''` says the old gloss was wrong and offers nothing to stand instead, so
    there is no example in it. Two judges agreeing to delete is a different question."""
    store = Store(tmp_path / "words.db")
    _judged(store, "author", "")
    _judged(store, "editor", "")
    assert store.agreed() == []


def test_judges_agree_only_on_the_same_answer_for_the_same_word(tmp_path: Path) -> None:
    """Two people correcting one word to two different senses is a disagreement, and the
    set must not quietly hold both."""
    store = Store(tmp_path / "words.db")
    _judged(store, "author", "with")
    _judged(store, "reader", "people")
    assert store.agreed() == []
    _judged(store, "editor", "with", term="אחר")
    _judged(store, "author", "with", term="אחר")
    assert [row["term"] for row in store.agreed()] == ["אחר"]


def test_the_agreed_set_can_be_narrowed_to_one_stage_and_written_out(tmp_path: Path) -> None:
    import json as json_module

    db = tmp_path / "words.db"
    store = Store(db)
    _judged(store, "author", "with")
    _judged(store, "reader", "with")
    _judged(store, "author", "רוצה", term="שרוצים", stage="lemma")
    _judged(store, "editor", "רוצה", term="שרוצים", stage="lemma")
    assert len(store.agreed()) == 2
    assert [row["term"] for row in store.agreed("lemma")] == ["שרוצים"]

    runner = CliRunner()
    out = tmp_path / "gold.json"
    said = runner.invoke(app, ["corrections", "--agreed", "--out", str(out), "--store", str(db)])
    assert said.exit_code == 0, said.output
    written = json_module.loads(out.read_text(encoding="utf-8"))
    assert len(written) == 2 and {row["term"] for row in written} == {"עם", "שרוצים"}
    assert "2 judges" in said.output

    quiet = runner.invoke(
        app, ["corrections", "--agreed", "--stage", "pointing", "--store", str(db)]
    )
    assert "Nothing two kinds of judge have agreed on yet." in quiet.output


# -- which judge, and which text (targum-internal#164, David 2026-09-22) ----------------


def test_a_judge_is_a_stable_pseudonym_and_never_the_account(tmp_path: Path) -> None:
    """`who` says what kind of judge; this says which one, without saying who they are.

    **Stable, not rotating.** A rotating salt would give one person a different pseudonym
    in each window, so two windows of one reader would read as two readers agreeing —
    manufacturing exactly the false corroboration the pseudonym exists to prevent.
    """
    store = Store(tmp_path / "words.db")
    mine = store.judge_for(7)
    assert mine == store.judge_for(7), "the same reader, the same judge, every time"
    assert mine != store.judge_for(8)
    # Sixteen hex digits of an HMAC: it carries the account id nowhere anybody can read,
    # and cannot be turned back into one without the salt.
    assert mine != "7" and len(mine) == 16 and set(mine) <= set("0123456789abcdef")

    # A second store over the same file keeps the salt, so the pseudonym survives a
    # restart — the thing a rotating salt would have broken.
    assert Store(tmp_path / "words.db").judge_for(7) == mine


def test_two_readers_agreeing_count_as_two_and_one_reader_twice_counts_as_one(
    tmp_path: Path,
) -> None:
    """The whole reason for the pseudonym. Before it, `who` was a bare role and this
    could only be counted by role, which made reader-corroborating-reader — most of the
    gold set — uncountable."""
    store = Store(tmp_path / "words.db")
    one, two = store.judge_for(1), store.judge_for(2)

    store.correct("gloss", who="reader", judge=one, term="עם", after="with")
    store.correct("gloss", who="reader", judge=one, term="עם", after="with")
    assert store.agreed() == [], "one reader saying it twice is one judge"

    store.correct("gloss", who="reader", judge=two, term="עם", after="with")
    found = store.agreed()
    assert len(found) == 1 and found[0]["judges"] == 2, "two readers is two judges"
    assert found[0]["seen"] == 3, "and all three rows are behind it"


def test_a_row_with_no_judge_still_counts_by_its_role(tmp_path: Path) -> None:
    """The author's hand has no account behind it, and every row written before the
    column existed has none either. Those count by role, as they did."""
    store = Store(tmp_path / "words.db")
    store.correct("gloss", who="author", term="עם", after="with")
    store.correct("gloss", who="reader", judge=store.judge_for(1), term="עם", after="with")
    assert len(store.agreed()) == 1, "the author and a reader are two judges"


def test_a_shut_texts_sentence_does_not_leave_but_its_judgement_does(tmp_path: Path) -> None:
    """Acceptance 5. The judgement is a fact about Hebrew and is targum's to give away;
    the sentence beside it is a piece of somebody's text."""
    from targum.accounts import exportable_corrections

    store = Store(tmp_path / "words.db")
    store.correct(
        "gloss", who="reader", term="עם", after="with", text="open-text", context="הלכתי עם אחי"
    )
    store.correct(
        "gloss", who="reader", term="עם", after="with", text="shut-text", context="משפט סודי"
    )
    store.correct("gloss", who="author", term="עם", after="with", context="no text at all")

    rows = exportable_corrections(store.corrections(), lambda text: text == "open-text")
    by_text = {str(row["text"]): row for row in rows}

    assert by_text["open-text"]["context"] == "הלכתי עם אחי"
    assert not by_text["open-text"].get("context_withheld")

    shut = by_text["shut-text"]
    assert shut["context"] == "", "the sentence does not leave"
    assert shut["context_withheld"] is True, "and the row says so rather than looking empty"
    assert shut["term"] == "עם" and shut["after"] == "with", "the judgement does leave"

    assert by_text[""]["context"] == "no text at all", "a row naming no text keeps its context"


def test_a_grounding_writes_the_text_it_happened_in_and_the_judge_who_made_it(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "words.db")
    note = grounding_note(store, "עם", "he", "en", text="genesis", judge="abc123")
    note(Sense(gloss="people"), Sense(gloss="with"), "הלכתי עם אחי")
    row = store.corrections()[0]
    assert row["text"] == "genesis" and row["judge"] == "abc123"
    assert row["who"] == "reader", "still a role, beside the pseudonym"


# -- door 3: a reader's proposal, behind the grant (targum-internal#164) ----------------


def test_a_reader_who_has_not_accepted_the_grant_has_not_granted(tmp_path: Path) -> None:
    """Acceptance 2's first half. The grant gates the *control*: a reader who has not
    met the sentence is never shown a way to offer a correction, so there is nothing to
    refuse afterwards."""
    store = Store(tmp_path / "words.db")
    made = store.sign_in_verified("reader@example.com")
    assert made is not None
    person, _ = made
    assert store.has_granted(person.id) is False
    store.grant(person.id)
    assert store.has_granted(person.id) is True
    assert store.has_granted(person.id + 999) is False, "and nobody is granted by default"


def test_a_proposal_carries_the_grant_it_arrived_under(tmp_path: Path) -> None:
    """Acceptance 2's second half. Recorded at the moment of the offer, because that is
    the one moment anybody knows which sentence was shown."""
    from targum.accounts import CONTRIBUTOR_GRANT

    store = Store(tmp_path / "words.db")
    made = store.propose_correction(
        stage="gloss", who="reader", term="עם", language="he", target="en", after="with"
    )
    row = next(r for r in store.corrections() if r["id"] == made)
    assert row["state"] == "proposed" and row["licence"] == CONTRIBUTOR_GRANT
    assert [r["id"] for r in store.proposed_corrections()] == [made]


def test_an_accepted_proposal_is_settled_and_counts_and_a_rejected_one_does_neither(
    tmp_path: Path,
) -> None:
    """Acceptance 3: an accepted proposal changes the gloss, a rejected one does not, and
    both are rows. The change to the gloss is the caller's; what is here is the record.

    And the part that matters for the gold set: a **rejected** proposal is a judgement
    that the suggestion was *wrong*, and an **unsettled** one is not a judgement at all.
    Counting either would let a reader put an answer into the gold set by suggesting it,
    which is exactly what this card's "not a vote" is guarding against.
    """
    store = Store(tmp_path / "words.db")
    kept = store.propose_correction(
        stage="gloss", who="reader", term="עם", language="he", target="en", after="with"
    )
    refused = store.propose_correction(
        stage="gloss", who="reader", term="אור", language="he", target="en", after="nonsense"
    )
    # A second judge agrees with each, so only the settlement can tell them apart.
    store.correct("gloss", who="author", term="עם", language="he", target="en", after="with")
    store.correct("gloss", who="author", term="אור", language="he", target="en", after="nonsense")
    assert store.agreed() == [], "a proposal nobody has settled is not a judgement yet"

    said_yes = store.settle_correction(kept, accept=True)
    said_no = store.settle_correction(refused, accept=False)

    by_id = {r["id"]: r for r in store.corrections()}
    assert by_id[kept]["state"] == "accepted" and by_id[refused]["state"] == "rejected"
    assert by_id[said_yes]["who"] == "author" and "accepted" in by_id[said_yes]["reason"]
    assert by_id[said_no]["who"] == "author" and "rejected" in by_id[said_no]["reason"]

    terms = [row["term"] for row in store.agreed()]
    assert terms == ["עם"], "the accepted one counts; the refused one never does"


def test_a_proposal_can_only_be_settled_once(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    made = store.propose_correction(stage="gloss", who="reader", term="עם", after="with")
    store.settle_correction(made, accept=True)
    with pytest.raises(KeyError):
        store.settle_correction(made, accept=False)


def test_the_command_settles_a_proposal_and_only_an_accepted_one_changes_the_gloss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 3 end to end: accepted changes the gloss, refused does not, both are
    rows. The gloss cache is pointed at a temp directory so nothing on this machine moves.
    """
    monkeypatch.setattr(gloss_module, "_home", lambda: tmp_path / "glosses", raising=False)
    monkeypatch.setenv("TARGUM_CACHE", str(tmp_path / "cache"))
    db = tmp_path / "words.db"
    store = Store(db)
    taken = store.propose_correction(
        stage="gloss", who="reader", term="עם", language="he", target="en", after="with"
    )
    refused = store.propose_correction(
        stage="gloss", who="reader", term="אור", language="he", target="en", after="nonsense"
    )

    runner = CliRunner()
    listed = runner.invoke(app, ["corrections", "--proposed", "--store", str(db)])
    assert listed.exit_code == 0, listed.output
    assert f"#{taken}" in listed.output and "reader-grant-2026-09-22" in listed.output

    yes = runner.invoke(app, ["settle", str(taken), "--accept", "--store", str(db)])
    assert yes.exit_code == 0, yes.output
    assert "Accepted" in yes.output and "with" in yes.output

    no = runner.invoke(app, ["settle", str(refused), "--reject", "--store", str(db)])
    assert no.exit_code == 0, no.output
    assert "Refused" in no.output and "stays as it was" in no.output

    assert store.proposed_corrections() == [], "the queue is empty once both are settled"

    # Accepting *is* the second judgement: the reader offered it and the author agreed,
    # which is two judges on the same answer and exactly what the gold set is for. The
    # refused one never reaches it, however many times it was written down.
    assert [row["term"] for row in store.agreed()] == ["עם"]
    assert all(row["term"] != "אור" for row in store.agreed())

    gone = runner.invoke(app, ["settle", str(taken), "--accept", "--store", str(db)])
    assert gone.exit_code != 0, "a proposal is settled once"
