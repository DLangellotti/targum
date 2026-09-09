"""A build you can walk away from.

The id of a build used to live only in the page that started it. Leaving that page made
the build look cancelled — it was not, but nothing could find it again, and the first
alpha reader reported exactly that: "clicking away from the page cancels it and user has
no idea what is going on".
"""

from __future__ import annotations

from pathlib import Path

from targum.accounts import Store, now
from targum.serve import Job, Library


class Postbox:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, link: str) -> None:
        raise AssertionError("a finished build is not a sign-in")

    def notify(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


def job(id: str, owner: int | None, stage: str, made: int, **extra: object) -> Job:
    return Job(id=id, source="s", title=f"Text {id}", owner=owner, stage=stage, made=made, **extra)  # type: ignore[arg-type]


def test_the_list_is_yours_and_says_how_far_back_you_are(tmp_path: Path) -> None:
    library = Library(tmp_path)
    library.jobs = {
        "a": job("a", 1, "working", 100),
        "b": job("b", 2, "queued", 200),
        "c": job("c", 1, "queued", 300),
        "d": job("d", 1, "done", now(), reader="d/reader/index.html"),
    }
    mine = library.mine(1)
    assert [j["id"] for j in mine] == ["d", "c", "a"], "newest first, and only mine"
    by_id = {j["id"]: j for j in mine}
    assert by_id["a"]["behind"] == 0, "the one being worked on"
    assert by_id["c"]["behind"] == 2, "behind the one working and the one queued before it"
    assert by_id["d"]["reader"] == "d/reader/index.html"
    assert "made" in by_id["d"], "the page sorts on it"


def test_a_build_finished_long_ago_is_not_on_the_list(tmp_path: Path) -> None:
    library = Library(tmp_path)
    library.jobs = {
        "old": job("old", 1, "done", now() - Library.RECENT_MS - 1),
        "new": job("new", 1, "done", now()),
        "priced": job("priced", 1, "ready", now()),
    }
    assert [j["id"] for j in library.mine(1)] == ["new"], (
        "and a build never started is not building"
    )


def test_a_long_build_says_so_by_email(tmp_path: Path) -> None:
    """The reader has most likely gone to do something else, and the page they started
    it from is gone. Two lines and a link, from the address the reader can reach."""
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    postbox = Postbox()
    library = Library(
        tmp_path,
        store=store,
        mailer=postbox,
        address="https://targum.page",  # type: ignore[arg-type]
    )
    long = job(
        "long", person.id, "done", now() - Library.LONG_BUILD_MS - 1, reader="a b/reader/index.html"
    )
    library.tell(long)
    assert len(postbox.sent) == 1
    to, subject, body = postbox.sent[0]
    assert to == "reader@example.com"
    assert subject == "Text long is ready"
    assert "https://targum.page/reader/a%20b/reader/index.html" in body


def test_a_short_build_says_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    postbox = Postbox()
    library = Library(tmp_path, store=store, mailer=postbox, address="https://targum.page")  # type: ignore[arg-type]
    library.tell(job("quick", person.id, "done", now() - 1000, reader="q/reader/index.html"))
    library.tell(job("nobody", None, "done", now() - Library.LONG_BUILD_MS - 1, reader="q/x"))
    assert postbox.sent == []


def test_a_failed_email_never_fails_the_build(tmp_path: Path) -> None:
    class Broken:
        def send(self, to: str, link: str) -> None:
            raise RuntimeError

        def notify(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("smtp is down")

    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    library = Library(tmp_path, store=store, mailer=Broken(), address="https://targum.page")  # type: ignore[arg-type]
    library.tell(job("long", person.id, "done", now() - Library.LONG_BUILD_MS - 1, reader="x/y"))


def test_putting_the_strip_away_is_a_promise_kept(tmp_path: Path) -> None:
    """Dismissing the pill says "you'll be updated by email". So a build the reader put
    away is told by email however short it was — and the list says whether that
    promise can be made at all."""
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    postbox = Postbox()
    library = Library(tmp_path, store=store, mailer=postbox, address="https://targum.page")  # type: ignore[arg-type]
    quick = job("quick", person.id, "done", now() - 1000, reader="q/reader/index.html")
    quick.options["mail"] = True
    library.tell(quick)
    assert [sent[1] for sent in postbox.sent] == ["Text quick is ready"]

    library.jobs = {"w": job("w", person.id, "working", now())}
    assert library.mine(person.id)[0]["mail"] is True
    assert Library(tmp_path).mine(None)[0:0] == [], "and nothing can be promised with no mailer"
    plain = Library(tmp_path)
    plain.jobs = {"w": job("w", None, "working", now())}
    assert plain.mine(None)[0]["mail"] is False


def test_the_line_is_not_answered_by_walking_history(tmp_path: Path) -> None:
    """A reader's place in the line costs the line, not everything ever run.

    Every chat turn is a job row, so the registry grows with every turn anybody takes.
    It used to be filtered on each call to find the two builds in the queue
    (targum-internal#231). The builds are indexed now, and a build that has been settled
    for longer than an hour leaves the index on the next sweep — the same condition
    `mine` uses to stop showing it, so there is only one rule.
    """
    library = Library(tmp_path)
    library.jobs.update(
        {f"chat-{n}": job(f"chat-{n}", 1, "done", now(), kind="chat") for n in range(5_000)}
    )
    library.jobs["old"] = job("old", 1, "done", now() - library.RECENT_MS - 1)
    library.jobs["a"] = job("a", 1, "working", 100)
    library.jobs["b"] = job("b", 1, "queued", 200)

    assert len(library.jobs) == 5_003, "the registry still holds everything"
    assert set(library.jobs.builds) == {"old", "a", "b"}, "a chat turn is never in the line"

    mine = library.mine(1)

    assert [one["id"] for one in mine] == ["b", "a"], "the settled one is an hour past"
    assert set(library.jobs.builds) == {"a", "b"}, "and has left the index on the way past"


def test_a_job_that_leaves_the_registry_leaves_the_index(tmp_path: Path) -> None:
    """Removal is noticed on the sweep rather than hooked on every route out."""
    library = Library(tmp_path)
    library.jobs["a"] = job("a", 1, "queued", 100)
    del library.jobs["a"]
    assert library.mine(1) == []
    assert library.jobs.builds == {}


def test_a_dict_assigned_over_the_registry_still_indexes(tmp_path: Path) -> None:
    """Several tests stage a queue by assigning a whole dict; that must not lose it."""
    library = Library(tmp_path)
    library.jobs = {"a": job("a", 1, "queued", 100), "c": job("c", 1, "done", now(), kind="chat")}
    assert set(library.jobs.builds) == {"a"}
    assert [one["id"] for one in library.mine(1)] == ["a"]
