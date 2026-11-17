"""A text under a NonCommercial licence stays free to read (David, 2026-11-17; design.md
§12).

Finds under CC BY-NC and CC BY-NC-SA may join the shared shelf, and an NC row must stay
readable without a plan. So, with plans on, building a library text whose own licence is
NonCommercial never needs a plan and never comes out of the month's credits, for Free or
Plan, while the money rails and the box ceiling still hold it through `claim`. Every other
text is held to the month exactly as before, and with plans off nothing changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import catalogue as catalogue_module
from targum import licensing
from targum.accounts import Person, Store
from targum.catalogue import Entry
from targum.serve import Job, Library

NC_VIDEO = "https://www.youtube.com/watch?v=ncvideo0001"
BY_VIDEO = "https://www.youtube.com/watch?v=byvideo0001"
JOINED_NC = "https://example.org/a-joined-nc-find"
HOUR = 3600.0


@pytest.mark.parametrize(
    ("licence", "free"),
    [
        ("CC BY-NC 4.0", True),
        ("CC BY-NC-SA 4.0", True),
        ("cc-by-nc-sa-3.0", True),
        ("Creative Commons Attribution-NonCommercial 4.0", True),
        ("CC BY-NC-ND 4.0", False),
        ("CC BY 4.0", False),
        ("CC BY-SA 4.0", False),
        ("public domain", False),
        ("", False),
        ("all rights reserved", False),
    ],
)
def test_noncommercial_is_read_as_verdict_reads_it(licence: str, free: bool) -> None:
    assert licensing.noncommercial(licence) is free


def entry(entry_id: str, source: str, licence: str) -> Entry:
    return Entry(
        id=entry_id,
        title=entry_id,
        author="",
        language="he",
        source=source,
        blurb="",
        words=500,
        licence=licence,
    )


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two catalogue videos, one under CC BY-NC-SA and one under CC BY."""
    rows = [
        *catalogue_module.CATALOGUE,
        entry("nc-video", NC_VIDEO, "CC BY-NC-SA 4.0"),
        entry("by-video", BY_VIDEO, "CC BY 4.0"),
    ]
    monkeypatch.setattr(catalogue_module, "CATALOGUE", rows)


def signed_up(store: Store, email: str) -> Person:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    return me


def a_library(tmp_path: Path, store: Store) -> Library:
    return Library(
        tmp_path / "out", max_cost=1000.0, budget=1000.0, store=store, account_budget=None
    )


def recording(library: Library, who: int, source: str, seconds: float, ident: str) -> Job:
    job = Job(
        id=ident,
        source=source,
        estimate=0.10,
        owner=who,
        home=library.out / "local",
        audio=True,
        seconds=seconds,
    )
    library.jobs[ident] = job
    library.remember(job)
    return job


def length(store: Store, ident: str) -> float:
    return float(store.db.execute("SELECT length FROM job WHERE id = ?", (ident,)).fetchone()[0])


@pytest.mark.usefixtures("shelf")
def test_on_free_an_nc_text_reads_without_a_plan_and_takes_no_credits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "free@example.com")
    nc = recording(library, me.id, NC_VIDEO, 3 * HOUR, "nc")
    assert library.free_to_read(nc)
    assert library.claim(nc) == "", "three hours, on Free's one"
    assert length(store, "nc") == 0.0, "and none of the month"
    assert store.hours_used(me.id, library._month_from()) == 0.0
    # The quote says so too: nothing refused, and the card is not metered.
    quoted = recording(library, me.id, NC_VIDEO, 3 * HOUR, "nc-quote")
    quoted.stage = "ready"
    library.short_of_month(quoted)
    assert quoted.stage == "ready"
    quoted.free_read = library.free_to_read(quoted)
    assert quoted.state()["metered"] is False


@pytest.mark.usefixtures("shelf")
def test_on_free_a_text_under_any_other_licence_is_held_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "free@example.com")
    by = recording(library, me.id, BY_VIDEO, 2 * HOUR, "by")
    assert not library.free_to_read(by)
    refused = library.claim(by)
    assert refused and refused.act == "plan", "Free's hour, and the plan offered"
    # An upload of the reader's own is not a library text, whatever it is.
    own = recording(library, me.id, "upload:mine.mp3", 2 * HOUR, "own")
    assert not library.free_to_read(own) and library.claim(own).act == "plan"
    # The free read leaves the month as it was: Free's 60 still buy 60 of anything else.
    assert library.claim(recording(library, me.id, NC_VIDEO, 5 * HOUR, "nc")) == ""
    assert library.claim(recording(library, me.id, BY_VIDEO, 50 * 60, "by-short")) == ""


@pytest.mark.usefixtures("shelf")
def test_the_money_rails_still_hold_an_nc_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Free to read is free of the month, not of the rails: the box ceiling and the
    reader's day still refuse it through `claim`."""
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = Library(
        tmp_path / "out", max_cost=1000.0, budget=0.05, store=store, account_budget=None
    )
    me = signed_up(store, "free@example.com")
    refused = library.claim(recording(library, me.id, NC_VIDEO, HOUR, "nc"))
    assert refused, "the box ceiling is nobody's to skip"
    capped = Library(
        tmp_path / "out2", max_cost=1000.0, budget=1000.0, store=store, account_budget=0.05
    )
    assert capped.claim(recording(capped, me.id, NC_VIDEO, HOUR, "nc-day"))


@pytest.mark.usefixtures("shelf")
def test_with_plans_off_nothing_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "a@example.com")
    nc = recording(library, me.id, NC_VIDEO, HOUR, "nc")
    assert not library.free_to_read(nc)
    assert library.claim(nc) == "" and length(store, "nc") == HOUR


@pytest.mark.usefixtures("shelf")
def test_a_gift_is_not_a_free_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "a@example.com")
    gift = recording(library, me.id, NC_VIDEO, HOUR, "gift")
    gift.gift = True
    assert not library.free_to_read(gift)


def test_a_joined_nc_find_reads_free_on_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A find under CC BY-NC that joined the shared shelf (`joined.json`, as
    `promote.join_find` writes it) is free to read like any NC row."""
    monkeypatch.setenv("TARGUM_PLANS", "1")
    shared = tmp_path / "shared"
    shared.mkdir()
    monkeypatch.setenv("TARGUM_SHARED_DIR", str(shared))
    row = {
        "id": "joined-nc-find",
        "title": "A find",
        "author": "",
        "language": "he",
        "source": JOINED_NC,
        "blurb": "",
        "english": "",
        "words": 400,
        "tags": [],
        "translations": [],
        "kind": "talk",
        "register": "modern",
        "licence": "CC BY-NC 4.0",
        "credit": "An outlet",
        "licence_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "added": "2026-11-17",
    }
    (shared / "joined.json").write_text(json.dumps({"entries": [row]}), encoding="utf-8")
    assert catalogue_module.matching(JOINED_NC) is not None
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "free@example.com")
    joined = recording(library, me.id, JOINED_NC, 2 * HOUR, "joined")
    assert library.free_to_read(joined) and library.claim(joined) == ""
    assert length(store, "joined") == 0.0


@pytest.mark.usefixtures("shelf")
def test_a_set_of_nc_texts_takes_no_credits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "free@example.com")
    jobs = [recording(library, me.id, NC_VIDEO, 2 * HOUR, f"set{n}") for n in range(2)]
    assert library.claim_set(jobs)[0] == ""
    assert store.hours_used(me.id, library._month_from()) == 0.0


@pytest.mark.usefixtures("shelf")
def test_a_post_brought_by_hand_under_an_nc_address_is_not_a_free_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is built is what the reader brought, whatever address it names."""
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "free@example.com")
    brought = recording(library, me.id, NC_VIDEO, HOUR, "brought")
    brought.options = {"post": {"fetched_by": "brought", "caption": "x"}}
    assert not library.free_to_read(brought)
