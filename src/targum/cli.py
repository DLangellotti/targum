"""The targum command line."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import config as config_module
from . import ingest
from . import segment as segment_module
from . import translate as translate_module
from .cache import Cache
from .errors import TargumError
from .ids import slug
from .models import Document, Style
from .paths import cache_dir, config_path, model_dir
from .pipeline import Build

if TYPE_CHECKING:
    from collections.abc import Callable

    from .annotate import Annotator

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "Read a text in the language you are learning, with a translation beside it.\n\n"
        "Start with: targum serve"
    ),
)
models_app = typer.Typer(no_args_is_help=True, help="Manage language models.")
cache_app = typer.Typer(no_args_is_help=True, help="Manage the cache.")
app.add_typer(models_app, name="models")
app.add_typer(cache_app, name="cache")

console = Console()
err = Console(stderr=True)


def _show_version(value: bool) -> None:
    """The first question anyone helping with a bug report asks."""
    if not value:
        return
    from importlib.metadata import PackageNotFoundError, version

    try:
        console.print(f"targum {version('targum')}")
    except PackageNotFoundError:  # running from a source tree
        console.print("targum (unpackaged source tree)")
    raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    return


# Above this, a run asks before it spends.
CONFIRM_ABOVE_USD = 0.50


def fail(error: TargumError) -> None:
    err.print(f"[red]{error.message}[/red]")
    if error.hint:
        err.print(f"[dim]{error.hint}[/dim]")
    raise typer.Exit(1)


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 8420,
    out: Annotated[Path | None, typer.Option("--out", help="Where your targums are kept.")] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the page automatically.")
    ] = True,
    max_cost: Annotated[
        float, typer.Option("--max-cost", help="Most one text may cost, in dollars.")
    ] = 2.00,
    budget: Annotated[
        float, typer.Option("--budget", help="Most this session may spend, in dollars.")
    ] = 10.00,
    store: Annotated[
        Path | None, typer.Option("--store", help="Where your words are kept.")
    ] = None,
) -> None:
    """Open a page for building targums, without the terminal."""
    from .serve import default_store, start

    directory = out or Path.cwd() / "targum-out"
    words = store or default_store()
    directory.mkdir(parents=True, exist_ok=True)

    # Hosted is configuration, not a different program. Set these in the deployment's
    # environment and `targum serve` is the public server; leave them and it is the
    # local one it has always been. Read before `announce` because what it should say
    # depends on which of the two this is.
    public = os.environ.get("TARGUM_PUBLIC_ADDRESS", "").strip()
    hosted = os.environ.get("TARGUM_REQUIRE_ACCOUNT", "").strip().lower() in {"1", "true", "yes"}

    def announce(address: str) -> None:
        # Hosted this goes to a journal rather than to somebody sitting in front of it,
        # and every line below is untrue there: there is no key in the address, the box
        # is reachable from everywhere on purpose, and nobody is going to press Ctrl-C.
        if hosted:
            console.print(f"[green]targum[/green] is serving [bold]{address}[/bold]")
            console.print(f"[dim]Words in {words}. Targums in {directory}.[/dim]")
            return
        # The key is part of the address, so it has to be printed with it — and it is
        # a different key every start, which is why a bookmark of this never works.
        console.print(f"[green]targum[/green] is at [bold]{address}[/bold]")
        console.print(
            "[dim]It should have opened by itself. This link changes every time targum "
            "starts, so open it from here rather than from a bookmark.[/dim]"
        )
        console.print(
            "[dim]Only this machine can reach it. Keep this window open while you read; "
            "Ctrl-C here stops it.[/dim]"
        )
        console.print(f"[dim]Your targums are saved in {directory}[/dim]")
        # Said separately from the readers, because it is somewhere else on purpose:
        # readers can be rebuilt and a word list cannot, so deleting the one must not
        # be a way of losing the other.
        console.print(f"[dim]Your words are kept in {words}, and stay there.[/dim]")
        console.print(
            f"[dim]Spending is capped at ${max_cost:.2f} per text and ${budget:.2f} this "
            f"session. You see the price before anything is spent.[/dim]"
        )

    if hosted and not os.environ.get("TARGUM_SMTP_HOST", "").strip():
        # Otherwise the door is shut and there is no way to knock: every route asks
        # for an account, and the only way to get one is a link nobody can send.
        fail(
            TargumError(
                "targum is set to require an account but has no way to send email.",
                "Set TARGUM_SMTP_HOST and its companions, or unset TARGUM_REQUIRE_ACCOUNT.",
            )
        )
    if hosted and not public:
        fail(
            TargumError(
                "targum is set to require an account but does not know its own address.",
                "Set TARGUM_PUBLIC_ADDRESS=https://targum.page, or the sign-in links it "
                "emails will point at the server's own loopback address.",
            )
        )

    try:
        start(
            directory,
            store=words,
            port=port,
            open_browser=open_browser,
            max_cost=max_cost,
            budget=budget,
            announce=announce,
            require_account=hosted,
            public_address=public,
        )
    except TargumError as error:
        fail(error)
    console.print(f"[dim]Stopped. Your targums are still in {directory}[/dim]")


@app.command()
def preflight(
    port: Annotated[int, typer.Option("--port", help="The port serve will bind.")] = 8420,
    out: Annotated[Path | None, typer.Option("--out", help="Where targums are kept.")] = None,
    store: Annotated[Path | None, typer.Option("--store", help="Where words are kept.")] = None,
    connect: Annotated[
        bool, typer.Option("--connect/--no-connect", help="Also try reaching the mail host.")
    ] = True,
) -> None:
    """Check a deployment before a reader does.

    A deployment fails either here, where it costs a minute, or at somebody's first
    sign-in, where it costs the only alpha reader there is. Run it after every deploy.
    Exits non-zero if anything would present a broken product, so a deploy script can
    stop on it.
    """
    from .preflight import fatal
    from .preflight import preflight as run
    from .serve import default_store

    words = store or default_store()
    directory = out or Path.cwd() / "targum-out"
    checks = run(words, directory, port=port, connect=connect)

    for check in checks:
        colour = {"ok": "green", "warn": "yellow", "FAIL": "red"}[check.state]
        console.print(f"[{colour}]{check.state:>4}[/{colour}]  {check.name:<24} {check.detail}")
        if check.fix and not check.ok:
            console.print(f"        [dim]{check.fix}[/dim]")

    broken = fatal(checks)
    if broken:
        console.print(f"\n[red]{len(broken)} of {len(checks)} would fail a reader.[/red]")
        raise typer.Exit(1)
    console.print(f"\n[green]Ready.[/green] [dim]{len(checks)} checks.[/dim]")


@app.command()
def invite(
    email: Annotated[str | None, typer.Argument(help="The address to let in.")] = None,
    remove: Annotated[
        str | None, typer.Option("--remove", help="Take an address off the list.")
    ] = None,
    store: Annotated[Path | None, typer.Option("--store", help="Which database.")] = None,
) -> None:
    """Say who may open an account.

    Hosted, nobody may until they are on this list — an empty list means nobody rather
    than everybody, so a box standing on a public address with a funded key does not let
    whoever finds it start spending. The first invitation is made here, on the box, which
    is what makes having the box the root of the whole thing.

    Taking an address off stops it opening a *new* account; anyone already reading keeps
    their words. Use the account-deletion path to remove a person.

    With no arguments, lists who is on it.
    """
    from .accounts import Store
    from .serve import default_store

    keeping = Store(store or default_store())

    if remove:
        gone = keeping.uninvite(remove)
        if gone:
            console.print(f"[green]Removed[/green] {remove}")
        else:
            console.print(f"[dim]{remove} was not on the list[/dim]")
        return

    if email:
        try:
            added = keeping.invite(email)
        except ValueError as error:
            fail(TargumError(str(error), "Try: targum invite someone@example.com"))
        console.print(f"[green]Invited[/green] {added}")
        return

    people = keeping.invitations()
    if not people:
        console.print("[dim]Nobody is invited. Hosted, that means nobody can join.[/dim]")
        return
    for person in people:
        console.print(person)
    console.print(f"[dim]{len(people)} invited[/dim]")


@app.command()
def admin(
    email: Annotated[
        str | None, typer.Argument(help="The address to put beyond the rails.")
    ] = None,
    remove: Annotated[
        str | None, typer.Option("--remove", help="Put an address back under them.")
    ] = None,
    store: Annotated[Path | None, typer.Option("--store", help="Which database.")] = None,
) -> None:
    """Say who runs this box.

    An admin is exempt from the per-account spend rails — the daily one and the monthly
    one — because those exist to stop a reader running up somebody else's bill, and the
    person paying it is not that reader. Nothing else is waived: the per-text cap and the
    whole-box daily ceiling still apply, and that ceiling is the runaway guard, which does
    not care whose account a loop is on.

    Making somebody an admin invites them too. An admin who cannot sign in is not one,
    and having to say it twice is a way of getting it half done.

    With no arguments, lists who is one.
    """
    from .accounts import Store
    from .serve import default_store

    keeping = Store(store or default_store())

    if remove:
        gone = keeping.unadmin(remove)
        if gone:
            console.print(f"[green]Removed[/green] {remove} [dim]— the invitation stays[/dim]")
        else:
            console.print(f"[dim]{remove} was not an admin[/dim]")
        return

    if email:
        try:
            added = keeping.make_admin(email)
        except ValueError as error:
            fail(TargumError(str(error), "Try: targum admin someone@example.com"))
        console.print(f"[green]Admin[/green] {added} [dim]— invited, and beyond the rails[/dim]")
        return

    people = keeping.admins()
    if not people:
        console.print("[dim]Nobody is an admin. Everyone is held to the spend rails.[/dim]")
        return
    for person in people:
        console.print(person)
    console.print(f"[dim]{len(people)} admin(s)[/dim]")


@app.command()
def usage(
    days: Annotated[
        int | None,
        typer.Option("--days", help="A rolling window instead of this calendar month."),
    ] = None,
    everything: Annotated[
        bool, typer.Option("--all", help="Since the beginning, rather than a window.")
    ] = False,
    store: Annotated[Path | None, typer.Option("--store", help="Which database.")] = None,
) -> None:
    """What targum has cost, and who it was spent on.

    The ledger is already kept — every build settles what the API really charged against
    what it reserved — and until now there was no way to read it but sqlite3. Somebody
    paying the bill should not have to.

    Two columns because they are two different facts. `spent` is what was really charged,
    which is what reconciles against an invoice. `held` is what the ceilings count: the
    same figure once a build has settled, its estimate while one is still running, and
    nothing for a build that failed and gave the reservation back.

    The default window is this calendar month, because that is the one the per-account
    cap is measured in.
    """
    from datetime import datetime

    from .accounts import Store, now
    from .serve import ACCOUNT_BUDGET, BUDGET_HOURS, MONTH_BUDGET, SESSION_BUDGET, default_store

    keeping = Store(store or default_store())

    if everything:
        since, window = 0, "all time"
    elif days:
        since = now() - days * 24 * 60 * 60 * 1000
        window = f"last {days} day(s)"
    else:
        today = datetime.now(UTC)
        since = int(datetime(today.year, today.month, 1, tzinfo=UTC).timestamp() * 1000)
        window = today.strftime("%B %Y")

    rows = keeping.spending(since)
    if not rows:
        console.print(f"[dim]Nothing spent — {window}.[/dim]")
        return

    admins = set(keeping.admins())
    table = Table(box=None, pad_edge=False)
    table.add_column("account")
    table.add_column("builds", justify="right")
    table.add_column("spent", justify="right")
    table.add_column("held", justify="right")
    table.add_column("last", justify="right")

    for row in rows:
        who = str(row["email"] or "")
        # A build with no account behind it is either older than accounts or belongs to
        # somebody since forgotten. Either way the money was real and belongs in the sum.
        label = who or "[dim]no account[/dim]"
        if who in admins:
            label = f"{who} [dim]admin[/dim]"
        last = row["last"] or 0
        when = (
            datetime.fromtimestamp(last / 1000, UTC).strftime("%-d %b") if last else "[dim]—[/dim]"
        )
        over = float(row["claimed"]) >= MONTH_BUDGET and who not in admins and not days
        holding = f"${float(row['claimed']):.2f}"
        table.add_row(
            label,
            str(row["jobs"]),
            f"${float(row['spent']):.2f}",
            f"[red]{holding}[/red]" if over else holding,
            when,
        )

    console.print(table)
    spent = sum(float(row["spent"]) for row in rows)
    held = sum(float(row["claimed"]) for row in rows)
    console.print(f"\n[bold]${spent:.2f}[/bold] spent · ${held:.2f} held [dim]— {window}[/dim]")
    console.print(
        f"[dim]Rails: ${MONTH_BUDGET:.2f} per account per month, "
        f"${ACCOUNT_BUDGET:.2f} per account per {BUDGET_HOURS}h, "
        f"${SESSION_BUDGET:.2f} for the whole box per {BUDGET_HOURS}h. "
        f"Admins are exempt from the first two.[/dim]"
    )


@app.command()
def backup(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where to keep copies. Default: ~/.targum/backups"),
    ] = None,
    store: Annotated[Path | None, typer.Option("--store", help="Which database to copy.")] = None,
    keep: Annotated[int, typer.Option("--keep", help="How many copies to keep.")] = 14,
    to: Annotated[
        str,
        typer.Option("--to", help="An rclone remote to send copies to. Or TARGUM_BACKUP_TO."),
    ] = "",
) -> None:
    """Copy the two things that cannot be rebuilt.

    The database first: accounts, saved words, phrases and the spend ledger live in one
    SQLite file and nowhere else. Then the translation cache, which is paid work — on a
    shared box it is what makes a public text free for the second reader and every reader
    after, so losing it means buying the same translations twice.

    Language models are skipped. They are downloads.

    Every copy is opened and checked as it is taken, because a backup nobody has opened
    is a rumour.

    `--to` is what gets them off this disk, through rclone — an S3 or B2 or R2 bucket, or
    SFTP to another machine. A copy written beside the database it copies survives every
    mistake and none of the disasters. Encryption belongs in the remote: a backup holds
    addresses and every word somebody has kept, so put an rclone `crypt` remote in front
    of the bucket rather than trusting the bucket.
    """
    from .backup import (
        NotShipped,
        archive_cache,
        check,
        check_archive,
        destination,
        ship,
        snapshot,
        sweep,
    )
    from .paths import cache_dir
    from .serve import default_store

    where = store or default_store()
    into = out or where.parent / "backups"
    try:
        made = snapshot(where, into)
    except FileNotFoundError:
        fail(TargumError(f"No database at {where}.", "Nothing has been saved yet."))
    except sqlite3.Error as error:
        fail(TargumError("Could not copy the database.", str(error)))

    problem = check(made)
    if problem:
        made.unlink(missing_ok=True)
        fail(TargumError("The copy came out unusable, so it was thrown away.", problem))

    size = made.stat().st_size / 1024
    console.print(f"[green]Copied to {made}[/green] [dim]({size:.0f} KB, checked)[/dim]")

    # The cache is the other half. A failure here must not lose the database copy that
    # already succeeded, so it reports and carries on rather than exiting.
    try:
        bundle = archive_cache(cache_dir(), into)
    except OSError as error:
        bundle = None
        console.print(f"[yellow]Could not copy the cache:[/yellow] [dim]{error}[/dim]")
    if bundle is not None:
        spoiled = check_archive(bundle)
        if spoiled:
            bundle.unlink(missing_ok=True)
            console.print(f"[yellow]The cache copy is unusable:[/yellow] [dim]{spoiled}[/dim]")
        else:
            mb = bundle.stat().st_size / 1024 / 1024
            console.print(
                f"[green]Cache copied to {bundle}[/green] [dim]({mb:.1f} MB, checked)[/dim]"
            )

    dropped = sweep(into, keep)
    if dropped:
        word = "copy" if len(dropped) == 1 else "copies"
        console.print(f"[dim]Dropped {len(dropped)} older {word}[/dim]")

    # Last, and only what this run produced: the point is that tonight's copy left, not
    # that the directory was synced. A failure here is a real failure — the copies on
    # disk are fine and the disaster they do not cover is the one this addresses — so it
    # exits non-zero and cron mails somebody.
    sending = destination(to)
    if not sending:
        console.print(
            "[yellow]These are on the same disk as the database.[/yellow] "
            "[dim]Set --to, or TARGUM_BACKUP_TO, to send them somewhere else.[/dim]"
        )
        return
    leaving = [path for path in (made, bundle) if path is not None and path.is_file()]
    try:
        arrived = ship(leaving, sending)
    except NotShipped as error:
        fail(TargumError("The copies did not leave the box.", str(error)))
    except (OSError, subprocess.SubprocessError) as error:
        fail(TargumError("The copies did not leave the box.", str(error)))
    console.print(f"[green]Sent to {sending}[/green] [dim]({', '.join(arrived)}, checked)[/dim]")


@app.command()
def restore(
    backup: Annotated[Path, typer.Argument(help="The copy to put back.")],
    store: Annotated[
        Path | None, typer.Option("--store", help="Which database to replace.")
    ] = None,
) -> None:
    """Put a backup back. Stop targum first.

    Takes either half: a `targum-*.db` snapshot or a `cache-*.zip` archive. The database
    replaces what is there, moving it aside rather than deleting it, because restoring
    the wrong file is a thing people do at four in the morning. The cache is unpacked
    *over* what is there instead — it is content-addressed, so an entry already present
    is the same entry, and anything bought since the copy was taken should survive.
    """
    from .backup import restore as put_back
    from .backup import restore_cache
    from .paths import cache_dir
    from .serve import default_store

    if backup.suffix == ".zip":
        try:
            written = restore_cache(backup, cache_dir())
        except ValueError as error:
            fail(TargumError(str(error), "Try an earlier copy."))
        console.print(f"[green]Restored {written} cached items to {cache_dir()}[/green]")
        console.print("[dim]Nothing already there was removed.[/dim]")
        return

    where = store or default_store()
    try:
        aside = put_back(backup, where)
    except ValueError as error:
        fail(TargumError(str(error), "Try an earlier copy."))

    console.print(f"[green]Restored {backup} to {where}[/green]")
    console.print(f"[dim]What was there is at {aside}[/dim]")


@app.command()
def warm(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where the built targums are. Default: ./targum-out"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="The model these were translated with."),
    ] = None,
) -> None:
    """Seed the shared cache from work already paid for, so nobody pays twice.

    A translation is cached under the exact run of segments it was asked for. Bought from
    the command line, a book is one run — the whole thing. Served, it is bought a chapter
    at a time, so the reader's build asks for a key that was never written and pays for a
    chapter of a book that is already translated and sitting on the disk.

    This writes the chapter-shaped keys from the translations already on disk. Nothing is
    fetched and nothing is spent: the English is the English that was bought.
    """
    from .cache import Cache
    from .catalogue import BOUGHT_WITH
    from .models import Document, SegmentedDocument, Translation, read_artifact
    from .pipeline import Build

    root = out or Path.cwd() / "targum-out"
    if not root.is_dir():
        fail(TargumError(f"No targums in {root}.", "Build one first: targum build"))

    cache = Cache()
    folders = [f for f in sorted(root.rglob("document.json"))]
    warmed = runs = 0
    for document_path in folders:
        folder = document_path.parent
        document = read_artifact(Document, document_path)
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if document is None or segmented is None:
            continue
        machine = [
            t
            for path in sorted((folder / "translations").glob("*.json"))
            if (t := read_artifact(Translation, path)) is not None and t.provider != "aligned"
        ]
        if not machine:
            continue
        translation = machine[0]
        builder = Build(
            document.source,
            target_language=translation.target_language,
            source_language=segmented.language,
            style=Style.natural,
            provider_name=translation.provider,
            model=model or translation.model or BOUGHT_WITH,
            owner="",
        )
        here = 0
        for number in range(1, 500):
            run = builder.chapter_segments(segmented, number)
            if not run:
                break
            have = {s.id: translation.segments[s.id] for s in run if translation.segments.get(s.id)}
            if len(have) != len(run):
                continue  # a chapter that was never finished is not one to promise
            cache.put("translate", builder.cache_key(segmented, run), {"segments": have})
            here += 1
        if here:
            warmed += 1
            runs += here
            console.print(f"[dim]  {document.title or folder.name} ({here} chapters)[/dim]")
    console.print(
        f"[green]Seeded {runs} chapter{'' if runs == 1 else 's'} from {warmed} "
        f"targum{'' if warmed == 1 else 's'}.[/green] "
        f"[dim]Nothing was fetched and nothing was spent.[/dim]"
    )


def _targums(where: Path) -> list[Path]:
    """Every targum under a library root, whichever home it sits in.

    Targums used to live directly under the root and now live one level down, in a
    directory per person. Looking only at the top finds the homes themselves and
    reports every one of them as having no text — which is what this did.
    """
    found: list[Path] = []
    for entry in where.iterdir():
        if not entry.is_dir():
            continue
        if (entry / "document.json").is_file():
            found.append(entry)
        else:
            found.extend(child for child in entry.iterdir() if child.is_dir())
    return found


@app.command()
def repair(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where your targums are. Default: ./targum-out"),
    ] = None,
) -> None:
    """Put back the spacing and the structure a source dropped, in texts already built.

    Two repairs, both of which ingest now does on the way in, and neither of which a
    text built beforehand has had. Words its source ran together are separated, and a
    text that arrived as plain prose with its section titles sitting in it as ordinary
    paragraphs gets those titles marked, which is what gives a reader its contents page.

    Rebuilding from the source would do both and would cost money: every stage is keyed
    to the Hebrew, so a sentence one space longer is a sentence nothing has translated.
    So the English is carried across by hand instead. Marking a heading does not change
    a word, and the sentence that gained a space is still the sentence its English was
    bought for; the two stages that do have to be redone — dictionary forms and vowel
    points — run on this machine, for the changed sentences only. Nothing is fetched and
    nothing is spent.
    """
    from .annotate import Annotator, PhonikudPronouncer, Pronouncer, biblical, pronounceable
    from .ingest.base import infer_headings
    from .ingest.spacing import unglue as respace
    from .models import (
        Alignment,
        Annotation,
        Block,
        Document,
        SegmentedDocument,
        Translation,
        Vocalization,
        glossaries_in,
        read_artifact,
    )
    from .render import render as render_reader
    from .vocalize import build as build_vocalizer
    from .vocalize import vocalize_document, wants_pointing

    root = out or Path.cwd() / "targum-out"
    if not root.is_dir():
        fail(TargumError(f"No targums in {root}.", "Build one first: targum serve"))

    done = words = titles = 0
    for folder in sorted(_targums(root)):
        if folder.name == "uploads":
            continue
        document = read_artifact(Document, folder / "document.json")
        if document is None:
            continue
        blocks = [
            block.model_copy(update={"text": respace(block.text, document.language)})
            for block in document.blocks
        ]
        repaired = sum(
            len(new.text.split()) - len(old.text.split())
            for new, old in zip(blocks, document.blocks, strict=True)
        )

        # Only where the source had no markup to state its structure with. What a text
        # arrived as is recorded on the artifact, so this does not have to guess — except
        # for artifacts written before the plain path had a name of its own, where the
        # address ending in .txt is what says it.
        arrived_as = document.ingester.split("/")[0]
        plain = arrived_as in ("text", "url-text") or (
            arrived_as == "url" and urlparse(document.source).path.endswith(".txt")
        )
        marked = 0
        if plain:
            inferred = infer_headings([(b.kind, b.level, b.text) for b in blocks], split=False)
            blocks = [
                Block(id=b.id, kind=kind, level=level, text=text)
                for b, (kind, level, text) in zip(blocks, inferred, strict=True)
            ]
            marked = sum(
                1 for b, old in zip(blocks, document.blocks, strict=True) if b.kind is not old.kind
            )

        if not repaired and not marked:
            continue

        document.blocks = blocks
        document.content_hash = document.recompute_hash()
        document.write(folder / "document.json")

        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if segmented is not None:
            kinds = {block.id: block for block in document.blocks}
            changed = []
            for segment in segmented.segments:
                text = respace(segment.text, segmented.language)
                if text != segment.text:
                    segment.text = text
                    changed.append(segment)
                block = kinds.get(segment.block_id)
                if block is not None:
                    segment.kind, segment.level = block.kind, block.level
            segmented.document_hash = document.content_hash
            segmented.write(folder / "segments.json")

            # Only the sentences that moved, and only the stages that run here. Both of
            # these are keyed to the whole document, so the artifact is patched in place
            # rather than rebuilt: redoing a book to fix one line in it is the cost this
            # command exists to avoid.
            patch = SegmentedDocument(
                document_hash=document.content_hash,
                language=segmented.language,
                segmenter=segmented.segmenter,
                segments=changed,
            )
            # Vowels before words, and for the same reason the pipeline does it in that
            # order: a sentence's reading is worked out from its pointing, so annotating
            # first would hand the repaired lines back without one while the rest of the
            # document kept theirs — a gap in the middle of a book, and nothing naming it.
            vocalization = read_artifact(Vocalization, folder / "vocalization.json")
            if vocalization is not None:
                if changed:
                    engine = build_vocalizer() if wants_pointing(changed) else None
                    fresh = vocalize_document(patch, engine)
                    vocalization.segments.update(fresh.segments)
                    moved = {segment.id for segment in changed}
                    vocalization.machine = [
                        sid for sid in vocalization.machine if sid not in moved
                    ] + fresh.machine
                    vocalization.rejected = [
                        sid for sid in vocalization.rejected if sid not in moved
                    ] + fresh.rejected
                vocalization.document_hash = document.content_hash
                vocalization.write(folder / "vocalization.json")

            annotation = read_artifact(Annotation, folder / "annotation.json")
            if annotation is not None:
                if changed:
                    pronouncer: Pronouncer | None = None
                    if vocalization is not None and pronounceable(segmented.language):
                        candidate = PhonikudPronouncer()
                        if candidate.available()[0]:
                            pronouncer = candidate
                    annotator = Annotator(
                        bands=biblical.for_source(document.source), pronouncer=pronouncer
                    )
                    annotation.tokens.update(annotator.annotate(patch, vocalization).tokens)
                    # The whole document's annotator, not the patch's. A file that says
                    # phonikud read it while a repaired paragraph has no readings is worse
                    # than one that says nothing did: the first is never redone.
                    annotation.annotator = annotator.name
                annotation.document_hash = document.content_hash
                annotation.write(folder / "annotation.json")

        # The English itself is untouched. What it is keyed to moved, and that is all
        # that is written here.
        translations = []
        for path in sorted((folder / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None:
                continue
            translation.document_hash = document.content_hash
            translation.write(path)
            translations.append(translation)
        for path in sorted((folder / "alignments").glob("*.json")):
            alignment = read_artifact(Alignment, path)
            if alignment is None:
                continue
            alignment.document_hash = document.content_hash
            alignment.write(path)

        done += 1
        words += repaired
        titles += marked
        if segmented is not None and translations:
            render_reader(
                document,
                segmented,
                translations,
                folder / "reader",
                annotation=read_artifact(Annotation, folder / "annotation.json"),
                glossaries=glossaries_in(folder),
                vocalization=read_artifact(Vocalization, folder / "vocalization.json"),
                covers=root / "thumbs",
            )
        console.print(
            f"[dim]  {document.title or folder.name} — {repaired} word(s), "
            f"{marked} heading(s)[/dim]"
        )

    console.print(
        f"[green]Separated {words} word{'' if words == 1 else 's'} and marked {titles} "
        f"heading{'' if titles == 1 else 's'} in {done} "
        f"targum{'' if done == 1 else 's'}.[/green] "
        f"[dim]Nothing was fetched and nothing was spent.[/dim]"
    )


def rebuild_one(
    folder: Path,
    *,
    reads: list[str] | None,
    covers: Path,
    annotate: Callable[[Path, Document], Annotator] | None = None,
) -> tuple[str, int] | tuple[None, str]:
    """Rewrite one reader from the artifacts beside it.

    Returns the title and how many files were written, or `(None, why)` where there
    was nothing to write: a folder with no text, or one that was priced and never
    paid for. Nothing is fetched and nothing is spent.

    `annotate`, given, names the annotator this machine would use for the text, and a
    reader whose words were worked out by an older one has them worked out again
    before it is written. That is the only path by which a change to what a word is
    reaches a text already on the shelf: a build compares the names itself, but a
    rebuild reads the annotation as it finds it.
    """
    from .models import (
        Annotation,
        SegmentedDocument,
        Translation,
        Vocalization,
        glossaries_in,
        read_artifact,
    )
    from .render import render as render_reader

    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if document is None or segmented is None:
        return None, "no text on disk"
    translations = [
        translation
        for path in sorted((folder / "translations").glob("*.json"))
        if (translation := read_artifact(Translation, path)) is not None
    ]
    if not translations:
        # Ingested and priced, then never paid for. There is nothing to read.
        return None, "never translated"
    annotation = read_artifact(Annotation, folder / "annotation.json")
    if annotation is not None and annotate is not None:
        annotator = annotate(folder, document)
        if annotation.annotator != annotator.name:
            vocalization = read_artifact(Vocalization, folder / "vocalization.json")
            annotation = annotator.annotate(segmented, vocalization)
            annotation.write(folder / "annotation.json")
    glossaries = glossaries_in(folder)
    if annotation is not None:
        # Meanings held in the cache since this reader was written — looked up from
        # another text, or bought by somebody else — are its for free. Filled in here
        # so a card opens with the meaning rather than a button, and written down so
        # the next rebuild has nothing to do.
        from .annotate.gloss import fill_from_cache
        from .models import glossary_path

        for target, grown in fill_from_cache(annotation, glossaries, reads or ["en"]).items():
            grown.write(glossary_path(folder, target))
            glossaries[target] = grown
    pages = render_reader(
        document,
        segmented,
        translations,
        folder / "reader",
        annotation=annotation,
        glossaries=glossaries,
        vocalization=read_artifact(Vocalization, folder / "vocalization.json"),
        covers=covers,
        # Which languages the person whose reader this is reads. A reader is a file, so
        # a change to that only reaches one when the file is written again — which is
        # what this is, and why the profile page ends by running it.
        reads=reads,
        # Written over rather than emptied first. This runs on a box with readers
        # open on it: the same segments produce the same section files under the
        # same names, so overwriting leaves nothing stale behind, and nobody has the
        # page they are reading deleted from under them for the moment it takes to
        # write the new one. A release that changed how sections are split would
        # leave the extra files of the old split behind, which is the trade.
        clean=False,
    )
    return document.title or folder.name, len(pages)


def rebuild_home(home: Path, *, reads: list[str] | None) -> int:
    """Every reader in one person's home, for the server to call when what they read
    changes. Quiet: nobody is at a terminal to read a line per text."""
    done = 0
    if not home.is_dir():
        return 0
    for folder in sorted(child for child in home.iterdir() if child.is_dir()):
        if folder.name == "uploads":
            continue
        title, _ = rebuild_one(folder, reads=reads, covers=home.parent / "thumbs")
        done += title is not None
    return done


@app.command()
def rebuild(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where your targums are. Default: ./targum-out"),
    ] = None,
    words: Annotated[
        bool,
        typer.Option(
            "--words",
            help="Work the words out again where a newer annotator would. Free: Stanza runs here.",
        ),
    ] = False,
) -> None:
    """Rewrite every reader from what is already on disk.

    targum bakes its stylesheet and its JavaScript into each reader as it writes it, so
    a reader built last month is still the reader targum wrote last month. This rewrites
    them all from the artifacts beside them: nothing is fetched and nothing is spent,
    and anything the reader has learned to do since arrives in the ones you already have.

    The words in a reader are what the annotator made of them on the day, and rewriting
    the page does not revisit that. `--words` does: a text whose dictionary forms were
    worked out by an older annotator has them worked out again, on this machine, before
    the page is written.
    """
    root = out or Path.cwd() / "targum-out"
    if not root.is_dir():
        fail(TargumError(f"No targums in {root}.", "Build one first: targum serve"))

    annotate: Callable[[Path, Document], Annotator] | None = None
    if words:
        from .annotate import (
            Annotator,
            PhonikudPronouncer,
            Pronouncer,
            StanzaLemmatizer,
            biblical,
            pronounceable,
        )
        from .models import Vocalization, read_artifact

        # One lemmatizer for the whole run: the model it loads is most of the cost, and
        # the bands are the only part that differs from one text to the next.
        lemmatizer = StanzaLemmatizer()
        phonikud = PhonikudPronouncer()
        has_phonikud = phonikud.available()[0]

        def annotate(folder: Path, document: Document) -> Annotator:
            pronouncer: Pronouncer | None = None
            if has_phonikud and pronounceable(document.language):
                if read_artifact(Vocalization, folder / "vocalization.json") is not None:
                    pronouncer = phonikud
            return Annotator(
                lemmatizer=lemmatizer,
                bands=biblical.for_source(document.source),
                pronouncer=pronouncer,
            )

    # Homes are named for the person whose they are — `p<id>`, or `local` for the shared
    # signed-out one. Asked once per home rather than once per targum.
    known: dict[str, list[str] | None] = {}

    def reading_of(home: str) -> list[str] | None:
        if home not in known:
            from .accounts import Store
            from .serve import default_store

            where = default_store()
            person = int(home[1:]) if home.startswith("p") and home[1:].isdigit() else 0
            allowed = Store(where).reads(person) if person and where.exists() else None
            known[home] = sorted(allowed) if allowed else None
        return known[home]

    done = 0
    skipped: list[tuple[str, str]] = []
    for folder in sorted(_targums(root)):
        if folder.name == "uploads":
            continue
        title, outcome = rebuild_one(
            folder,
            reads=reading_of(folder.parent.name),
            covers=root / "thumbs",
            annotate=annotate,
        )
        if title is None:
            skipped.append((folder.name, str(outcome)))
            continue
        done += 1
        console.print(f"[dim]  {title} ({outcome} file{'' if outcome == 1 else 's'})[/dim]")

    for name, why in skipped:
        console.print(f"[dim]  skipped {name} — {why}[/dim]")
    console.print(
        f"[green]Rewrote {done} targum{'' if done == 1 else 's'}.[/green] "
        f"[dim]Nothing was fetched and nothing was spent.[/dim]"
    )


@app.command()
def build(
    # A string, not a Path: pathlib collapses the double slash in https:// and would
    # quietly turn every link into a missing file.
    source: Annotated[
        str, typer.Argument(help="A file, a link, or gutenberg:/wikisource: by name.")
    ],
    to: Annotated[
        str,
        typer.Option("--to", help="Translate into: he, ru, en, ar, fr, es, de, la."),
    ] = "en",
    source_language: Annotated[
        str | None,
        typer.Option("--from", help="Source language. Detected from the script if omitted."),
    ] = None,
    style: Annotated[
        Style,
        typer.Option(
            "--style",
            help="natural: idiomatic English. direct: close to the original's structure.",
        ),
    ] = Style.natural,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Translation provider. Default: anthropic."),
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="Provider model id.")] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Folder for the targum and its files. Default: ./targum-out/<title>-<lang>/",
        ),
    ] = None,
    translation: Annotated[
        list[Path] | None,
        typer.Option(
            "--translation",
            help="An existing translation to align. Repeat for several.",
        ),
    ] = None,
    machine: Annotated[
        bool | None,
        typer.Option(
            "--machine/--no-machine",
            help="Also machine-translate. On by default only when no --translation is given.",
        ),
    ] = None,
    words: Annotated[
        bool,
        typer.Option(
            "--words",
            help="Make every word tappable, with its dictionary form and difficulty.",
        ),
    ] = False,
    gloss: Annotated[
        bool,
        typer.Option(
            "--gloss",
            help="Look up every word up front. Costs money, and implies --words. "
            "Reading through targum serve, you can look words up one at a time instead.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Rebuild from scratch, ignoring anything cached."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask before spending.")] = False,
) -> None:
    """Build a targum — one text with its translation beside it."""
    # Inside the try, not before it. A mistyped --provider, or a stray key in the
    # config file, raised straight through Typer as a traceback: the one-line
    # message those errors carry never reached anyone.
    try:
        settings = config_module.load()
        # A text the catalogue knows is described by the catalogue, and two of the things
        # it knows matter here. Its title, because a plain .txt carries none and a reader
        # built from the command line then opens with no name at the top of it. And the
        # model its English was bought with — the cache is keyed on the model, so a build
        # that names a different one translates the whole book again at the reader's
        # expense. The server has always read both from here; the command line did not,
        # and had no way to know it was buying something already paid for.
        from . import catalogue as catalogue_module

        known = catalogue_module.matching(source)
        builder = Build(
            source,
            target_language=to,
            source_language=source_language,
            style=style,
            title=known.title if known else "",
            provider_name=provider or settings.provider,
            model=model or (known.model if known else "") or settings.model,
            out=out or (Path(settings.out) if settings.out else None),
            force=force,
            batch_size=settings.batch_size,
            effort=settings.effort,
            translations=translation or [],
            machine=machine,
            difficulty=words,
            gloss=gloss,
            notify=lambda message: console.print(f"[dim]{message}[/dim]"),
        )

        if words or gloss:
            from .annotate import frequency_available
            from .annotate.frequency import MISSING

            if not frequency_available():
                raise TargumError(*MISSING)

        with console.status("Reading and segmenting..."):
            plan = builder.plan()

        # After ingest, not before it. Checked first, a .pdf and a file that is not
        # there both answered "Provider 'anthropic' is not ready", which is neither
        # the problem nor a thing anyone can act on.
        usable, detail = builder.provider.available()
        if builder.machine and not usable:
            raise TargumError(f"Provider '{builder.provider_name}' is not ready.", detail)

        count = len(plan.segmented.segments) if plan.segmented else 0
        console.print(
            f"[bold]{plan.document.title or Path(source).name}[/bold] "
            f"[dim]{plan.document.language} → {to}, {count} segments[/dim]"
        )

        if plan.needs_payment:
            console.print(f"[dim]Estimated cost: about ${plan.estimated_cost:.2f}[/dim]")
            if plan.estimated_cost > CONFIRM_ABOVE_USD and not yes:
                if not typer.confirm(
                    f"Translate for about ${plan.estimated_cost:.2f}?", default=True
                ):
                    raise typer.Abort()

        if plan.cached_translation is not None:
            result = builder.run(plan)
        else:
            with Progress(
                TextColumn("[dim]translating[/dim]"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("translate", total=count)
                result = builder.run(plan, lambda done: progress.advance(task, done))
    except TargumError as error:
        fail(error)

    if result.glossary is not None:
        console.print(f"[dim]  {len(result.glossary.entries)} words glossed[/dim]")
    if result.annotation is not None:
        from .annotate import BAND_NAMES, method_label

        annotation = result.annotation
        total = sum(annotation.counts().values())
        if annotation.method == "none":
            console.print(f"[dim]  {total} words tappable, {method_label('none')}[/dim]")
        else:
            spread = ", ".join(
                f"{count} {BAND_NAMES.get(level, level)}"
                for level, count in annotation.counts().items()
            )
            console.print(
                f"[dim]  {total} words tappable, rated "
                f"{method_label(annotation.method)}: {spread}[/dim]"
            )
    for item in result.translations:
        coarse = f", {len(item.coarse)} paragraph-paired" if item.coarse else ""
        console.print(f"[dim]  {item.name} ({item.kind}{coarse})[/dim]")
    if result.reused:
        console.print(f"[dim]Reused: {', '.join(result.reused)}[/dim]")
    pages = len(result.pages) - (0 if len(result.pages) == 1 else 1)
    console.print(
        f"[green]Done.[/green] Open {result.index} in a browser "
        f"[dim]({pages} part{'' if pages == 1 else 's'})[/dim]"
    )


@app.command()
def fetch(
    source: Annotated[
        str, typer.Argument(help="A file, a link, or gutenberg:/wikisource: by name.")
    ],
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the file.")] = None,
) -> None:
    """Download a public domain text to a markdown file you can edit, then build."""
    try:
        with console.status(f"Fetching {source}..."):
            document = ingest.load(source)
        path = out or Path.cwd() / f"{slug(document.title or source)}.{document.language}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ingest.to_markdown(document), encoding="utf-8")
    except TargumError as error:
        fail(error)

    words = sum(len(block.text.split()) for block in document.blocks)
    console.print(
        f"[green]Wrote[/green] {path} "
        f"[dim]{document.language}, {len(document.blocks)} blocks, ~{words:,} words[/dim]"
    )
    console.print(f"[dim]targum build {path} --to en[/dim]")


@app.command(name="gloss")
def gloss_command(
    source: Annotated[str, typer.Argument(help="The text to look words up in: a file or a link.")],
    to: Annotated[str, typer.Option("--to", help="Language to gloss into.")] = "en",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Count the words and the cost, spend nothing.")
    ] = False,
    from_level: Annotated[
        int,
        typer.Option(
            "--from-level",
            min=1,
            max=6,
            help="Only look up words this rare or rarer: 1 everyday, 6 rare.",
        ),
    ] = 1,
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the glossary.")] = None,
) -> None:
    """Look up every word in a text, and cache the results across every text."""
    from .annotate import BAND_NAMES, Annotator, frequency_available
    from .annotate.frequency import MISSING
    from .annotate.gloss import AnthropicGlosses, build_glossary, estimate, unique_lemmas
    from .segment import StanzaSegmenter, segment_document

    try:
        if not frequency_available():
            raise TargumError(*MISSING)
        with console.status("Reading, segmenting and lemmatizing..."):
            document = ingest.load(source)
            segmented = segment_document(document, StanzaSegmenter())
            annotation = Annotator().annotate(segmented)

        lemmas = unique_lemmas(annotation, min_band=from_level)
        provider = AnthropicGlosses()
        tokens = sum(len(items) for items in annotation.tokens.values())
        cost = estimate(len(lemmas), provider.model)

        console.print(
            f"[bold]{document.title or Path(source).name}[/bold] "
            f"[dim]{tokens} words, {len(lemmas)} distinct dictionary forms"
            f"{f' rated {BAND_NAMES[from_level]} or rarer' if from_level > 1 else ''}[/dim]"
        )
        console.print(f"[dim]Glossing all of them would cost about ${cost:.2f} at most.[/dim]")
        console.print("[dim]Anything already glossed in this language pair is free.[/dim]")
        if dry_run:
            return

        usable, detail = provider.available()
        if not usable:
            raise TargumError("The Anthropic provider is not ready.", detail)
        if cost > CONFIRM_ABOVE_USD and not typer.confirm("Look them up?", default=True):
            raise typer.Abort()

        with Progress(
            TextColumn("[dim]glossing[/dim]"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("gloss", total=len(lemmas))
            glossary, paid = build_glossary(
                annotation,
                to,
                provider,
                min_band=from_level,
                on_progress=lambda n: progress.advance(task, n),
            )
    except TargumError as error:
        fail(error)

    path = out or Path.cwd() / f"{slug(Path(source).stem)}.{to}.glossary.json"
    glossary.write(path)
    console.print(
        f"[green]Wrote[/green] {path} "
        f"[dim]{len(glossary.entries)} glossed, {len(lemmas) - paid} already cached[/dim]"
    )


@app.command()
def align(
    source: Annotated[Path, typer.Argument(help="The original text.")],
    translation: Annotated[Path, typer.Argument(help="An existing translation of it.")],
    out: Annotated[Path | None, typer.Option("--out", help="Where to write the alignment.")] = None,
) -> None:
    """Align an existing translation to a source, and report how well it went."""
    from . import align as align_module
    from .segment import StanzaSegmenter, segment_document

    try:
        segmenter = StanzaSegmenter()
        with console.status("Reading and segmenting..."):
            source_document = ingest.load(str(source))
            target_document = ingest.load(str(translation))
            segmented = segment_document(source_document, segmenter)
            target = segment_document(target_document, segmenter)

        with console.status("Aligning..."):
            alignment = align_module.align(
                segmented, target, target_document.title or translation.stem
            )
    except TargumError as error:
        fail(error)

    path = out or Path.cwd() / f"{slug(source.stem)}.{target.language}.alignment.json"
    alignment.write(path)

    shapes: dict[str, int] = {}
    for link in alignment.links:
        shapes[link.kind] = shapes.get(link.kind, 0) + 1
    coarse = sum(1 for link in alignment.links if link.coarse)
    confident = sum(1 for link in alignment.links if link.confidence >= 0.5)

    console.print(
        f"[bold]{segmented.language} → {target.language}[/bold] "
        f"[dim]{len(segmented.segments)} against {len(target.segments)} segments[/dim]"
    )
    console.print(
        f"[dim]{len(alignment.links)} links: "
        f"{', '.join(f'{count}×{shape}' for shape, count in sorted(shapes.items()))}[/dim]"
    )
    console.print(
        f"[dim]{confident} confident, {coarse} collapsed to paragraphs, "
        f"length ratio {alignment.length_ratio}[/dim]"
    )
    console.print(f"[green]Wrote[/green] {path}")


@app.command()
def sources() -> None:
    """List everything targum can read."""
    console.print("  [bold]Files[/bold]      .epub, .txt, .md")
    console.print("  [bold]Links[/bold]      any article, essay or wiki page")
    console.print("  [bold]By name[/bold]    gutenberg:<number>, wikisource:<language>:<title>")
    console.print("[dim]Not PDF. Save one as text or markdown first.[/dim]")


@app.command()
def providers() -> None:
    """List translation providers and whether they can be used right now."""
    table = Table(box=None, pad_edge=False)
    table.add_column("provider")
    table.add_column("ready")
    table.add_column("")
    for name in translate_module.names():
        instance = translate_module.build(name)
        usable, detail = instance.available()
        table.add_row(name, "[green]yes[/green]" if usable else "[yellow]no[/yellow]", detail)
    console.print(table)
    console.print(f"[dim]Settings file: {config_path()} (optional)[/dim]")


@models_app.command("list")
def models_list() -> None:
    """Show downloaded language models."""
    from .align import embedding

    for name in embedding.downloaded_models():
        console.print(f"  {name}  [dim]{embedding.model_size(name) / 1_000_000:.0f} MB[/dim]")

    languages = segment_module.downloaded_languages()
    if not languages and not embedding.downloaded_models():
        console.print("[dim]No language models downloaded yet.[/dim]")
        console.print("[dim]They download on first use, or run: targum models fetch he[/dim]")
        return
    for language in languages:
        size = sum(f.stat().st_size for f in (model_dir() / language).rglob("*") if f.is_file())
        console.print(f"  {language}  [dim]{size / 1_000_000:.0f} MB[/dim]")
    console.print(f"[dim]{model_dir()}[/dim]")


@models_app.command("fetch")
def models_fetch(
    language: Annotated[str, typer.Argument(help="A language tag, such as he or ru.")],
) -> None:
    """Download a language model ahead of time. Use 'embeddings' for the aligner."""
    from .align import embedding

    if language in {"embeddings", "align", "aligner"}:
        if embedding.is_downloaded():
            console.print("[dim]The embedding model is already downloaded.[/dim]")
            return
        console.print(f"[dim]Fetching {embedding.DEFAULT_MODEL}, about 1.8 GB…[/dim]")
        try:
            embedding.SentenceTransformerEncoder().encoder()
        except TargumError as error:
            fail(error)
        console.print(f"[green]Downloaded[/green] {embedding.DEFAULT_MODEL}")
        return

    code = segment_module.stanza_code(language)
    from .annotate.lemma import PROCESSORS

    if segment_module.has_processors(code, PROCESSORS):
        console.print(f"[dim]{code} is already downloaded.[/dim]")
        return
    try:
        segment_module.download(code, processors=PROCESSORS)
    except TargumError as error:
        fail(error)
    console.print(f"[green]Downloaded[/green] {code}")


@models_app.command("remove")
def models_remove(language: Annotated[str, typer.Argument()]) -> None:
    """Delete a downloaded language model."""
    code = segment_module.stanza_code(language)
    if segment_module.remove(code):
        console.print(f"[green]Removed[/green] {code}")
    else:
        console.print(f"[dim]{code} was not downloaded.[/dim]")


@cache_app.command("clear")
def cache_clear(
    force: Annotated[
        bool, typer.Option("--force", help="Clear it anyway on a hosted box.")
    ] = False,
) -> None:
    """Drop cached translations. Language models are kept.

    On a machine one person runs, this frees disk and costs them a rebuild. On a hosted
    box it is a command that deletes money: the cache is what makes a public text free
    for the second reader and every reader after, so clearing it means every one of them
    buys the same translations again. Hosted, it asks first.
    """
    hosted = os.environ.get("TARGUM_REQUIRE_ACCOUNT", "").strip().lower() in {"1", "true", "yes"}
    if hosted and not force:
        fail(
            TargumError(
                "This is a hosted box, and the cache is paid work.",
                "Everyone who has read a public text would pay for it again. "
                "Take a backup first, then `targum cache clear --force`.",
            )
        )
    removed = Cache().clear()
    console.print(f"[green]Cleared[/green] {removed} cached items [dim]{cache_dir()}[/dim]")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        err.print("[dim]Stopped. Anything that finished earlier is cached.[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
