"""What the reader got wrong, kept (targum-internal#290).

Dmitry Z, 2026-09-16, on why a scheduler does not work for him: "anki srs is kinda dumb
in the sense it doesnt really know what you get wrong beyond what you tell it". A
scheduler only knows what you type into it. targum sits in the one place where a mistake
is visible without anybody typing anything — the reader writes a line of Hebrew and the
model rewrites it — and that correction used to be shown once and thrown away.

Most of what is asserted here is the half that must never happen: a correct line kept as
a mistake, a slip reaching the record of judgements about Hebrew, or a slip outliving the
account it belongs to.
"""

from __future__ import annotations

from pathlib import Path

from targum.accounts import Store
from targum.chat.record import changed_words, rewritten


def reader(tmp_path: Path):
    store = Store(tmp_path / "w.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    return store, signed[0]


# --- the diff -------------------------------------------------------------------------


def test_a_line_that_only_gained_its_points_is_not_a_mistake() -> None:
    """The model points every word it writes and the reader almost never does, so a
    string compare would call every correct line a correction. The one thing this must
    never do is report a mistake that did not happen."""
    assert not rewritten("אני הולך הביתה", "אֲנִי הוֹלֵךְ הַבַּיְתָה")
    assert changed_words("אני הולך הביתה", "אֲנִי הוֹלֵךְ הַבַּיְתָה") == []


def test_a_full_stop_is_not_a_correction() -> None:
    """A recast is a clean sentence and a reader's line often is not."""
    assert not rewritten("אני הולך", "אֲנִי הוֹלֵךְ.")


def test_a_wrong_form_is_the_word_that_replaced_it() -> None:
    """The card's own example: "אני הלך אתמול" comes back with the past tense, and what
    is kept is the token that changed rather than the whole line."""
    wrote, recast = "אני הלך אתמול", "אֲנִי הָלַכְתִּי אֶתְמוֹל"
    assert rewritten(wrote, recast)
    assert changed_words(wrote, recast) == ["הָלַכְתִּי"]


def test_word_order_alone_is_a_mistake_without_a_changed_word() -> None:
    """Hebrew word order is one of the things a recast fixes, and a reader who wrote the
    right words in the wrong order has made a mistake worth keeping — but the words
    themselves are not what changed, and listing all of them would say they all were."""
    wrote, recast = "הביתה הולך אני", "אֲנִי הוֹלֵךְ הַבַּיְתָה"
    assert not rewritten(wrote, recast), "the same words, so no word changed"
    assert changed_words(wrote, recast) == []


def test_a_missing_word_is_the_word_that_appeared() -> None:
    assert changed_words("אני הביתה", "אֲנִי הוֹלֵךְ הַבַּיְתָה") == ["הוֹלֵךְ"]


# --- the store ------------------------------------------------------------------------


def test_a_slip_is_kept_with_what_was_written_and_what_came_back(tmp_path: Path) -> None:
    store, who = reader(tmp_path)
    person = who.id
    store.slip(
        person,
        wrote="אני הלך אתמול",
        recast="אֲנִי הָלַכְתִּי אֶתְמוֹל",
        changed=["הָלַכְתִּי"],
        chat="c1",
        turn=3,
        why="Past tense: הָלַכְתִּי, not הָלַךְ.",
    )
    kept = store.slips(person)
    assert len(kept) == 1
    assert kept[0]["wrote"] == "אני הלך אתמול"
    assert kept[0]["recast"] == "אֲנִי הָלַכְתִּי אֶתְמוֹל"
    assert kept[0]["changed"] == ["הָלַכְתִּי"], "a list, not the JSON it is stored as"
    assert kept[0]["why"].startswith("Past tense")
    assert kept[0]["chat"] == "c1" and kept[0]["turn"] == 3


def test_the_queue_reads_them_oldest_first(tmp_path: Path) -> None:
    """The same order the word queue takes, for the same reason: what has been sitting
    there longest is what is worth coming back to."""
    store, who = reader(tmp_path)
    person = who.id
    for line in ("first", "second", "third"):
        store.slip(person, wrote=line, recast=line + "!", changed=[line])
    assert [row["wrote"] for row in store.slips(person, oldest=True)] == [
        "first",
        "second",
        "third",
    ]
    assert [row["wrote"] for row in store.slips(person)][0] == "third"


def test_nobody_elses_slips_come_back(tmp_path: Path) -> None:
    store, who = reader(tmp_path)
    person = who.id
    other = store.finish_sign_in(store.start_sign_in("other@example.com"))
    assert other is not None
    store.slip(person, wrote="mine", recast="mine!", changed=["mine"])
    store.slip(other[0].id, wrote="theirs", recast="theirs!", changed=["theirs"])
    assert [row["wrote"] for row in store.slips(person)] == ["mine"]
    assert [row["wrote"] for row in store.slips(other[0].id)] == ["theirs"]
    assert store.slips(None) == [], "and signed out there is nobody to have any"


# --- whose they are -------------------------------------------------------------------


def test_the_export_carries_them_and_forgetting_takes_them_away(tmp_path: Path) -> None:
    """The most personal rows in the database: a record of a learner's own mistakes, in
    their own sentences. So the first thing that had to be true is that somebody can take
    them away, and the second is that they go when the account does."""
    store, person = reader(tmp_path)
    person_id = person.id
    store.slip(person_id, wrote="אני הלך", recast="אֲנִי הָלַכְתִּי", changed=["הָלַכְתִּי"])

    everything = store.everything(person)
    assert [row["wrote"] for row in everything["slips"]] == ["אני הלך"]

    store.forget(person)
    store.purge(days=-1)
    assert store.slips(person_id) == []


def test_a_slip_never_reaches_the_record_of_judgements_about_hebrew(tmp_path: Path) -> None:
    """`correction` is #164: what was decided about the language, where `who` is a role
    and never a person, so that what it holds can be reasoned about as evidence. A
    learner's own mistakes are a fact about the learner and would poison it."""
    store, who = reader(tmp_path)
    person = who.id
    store.slip(person, wrote="אני הלך", recast="אֲנִי הָלַכְתִּי", changed=["הָלַכְתִּי"])
    assert store.corrections() == []
