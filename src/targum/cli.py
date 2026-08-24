"""The targum command line."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Annotated

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
from .models import Style
from .paths import cache_dir, config_path, model_dir
from .pipeline import Build

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

    def announce(address: str) -> None:
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

    # Hosted is configuration, not a different program. Set these in the deployment's
    # environment and `targum serve` is the public server; leave them and it is the
    # local one it has always been.
    public = os.environ.get("TARGUM_PUBLIC_ADDRESS", "").strip()
    hosted = os.environ.get("TARGUM_REQUIRE_ACCOUNT", "").strip().lower() in {"1", "true", "yes"}
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
def backup(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where to keep copies. Default: ~/.targum/backups"),
    ] = None,
    store: Annotated[Path | None, typer.Option("--store", help="Which database to copy.")] = None,
    keep: Annotated[int, typer.Option("--keep", help="How many copies to keep.")] = 14,
) -> None:
    """Copy the one file that cannot be rebuilt.

    Accounts, saved words, phrases and the spend ledger live in one SQLite file and
    nowhere else. Everything else targum keeps can be made again.

    Every copy is opened and checked as it is taken, because a backup nobody has opened
    is a rumour. Run it from cron, and keep the copies somewhere other than this machine.
    """
    from .backup import check, snapshot, sweep
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

    dropped = sweep(into, keep)
    size = made.stat().st_size / 1024
    console.print(f"[green]Copied to {made}[/green] [dim]({size:.0f} KB, checked)[/dim]")
    if dropped:
        word = "copy" if len(dropped) == 1 else "copies"
        console.print(f"[dim]Dropped {len(dropped)} older {word}[/dim]")
    console.print("[dim]Keep these somewhere other than this machine.[/dim]")


@app.command()
def restore(
    backup: Annotated[Path, typer.Argument(help="The copy to put back.")],
    store: Annotated[
        Path | None, typer.Option("--store", help="Which database to replace.")
    ] = None,
) -> None:
    """Put a backup back. Stop targum first.

    What is there now is moved aside rather than deleted: restoring the wrong file is a
    thing people do at four in the morning.
    """
    from .backup import restore as put_back
    from .serve import default_store

    where = store or default_store()
    try:
        aside = put_back(backup, where)
    except ValueError as error:
        fail(TargumError(str(error), "Try an earlier copy."))

    console.print(f"[green]Restored {backup} to {where}[/green]")
    console.print(f"[dim]What was there is at {aside}[/dim]")


@app.command()
def rebuild(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where your targums are. Default: ./targum-out"),
    ] = None,
) -> None:
    """Rewrite every reader from what is already on disk.

    targum bakes its stylesheet and its JavaScript into each reader as it writes it, so
    a reader built last month is still the reader targum wrote last month. This rewrites
    them all from the artifacts beside them: nothing is fetched and nothing is spent,
    and anything the reader has learned to do since arrives in the ones you already have.
    """
    from .models import (
        Annotation,
        Document,
        Glossary,
        SegmentedDocument,
        Translation,
        Vocalization,
        read_artifact,
    )
    from .render import render as render_reader

    root = out or Path.cwd() / "targum-out"
    if not root.is_dir():
        fail(TargumError(f"No targums in {root}.", "Build one first: targum serve"))

    def targums(where: Path) -> list[Path]:
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

    done = 0
    skipped: list[tuple[str, str]] = []
    for folder in sorted(targums(root)):
        if folder.name == "uploads":
            continue
        document = read_artifact(Document, folder / "document.json")
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if document is None or segmented is None:
            skipped.append((folder.name, "no text on disk"))
            continue
        translations = [
            translation
            for path in sorted((folder / "translations").glob("*.json"))
            if (translation := read_artifact(Translation, path)) is not None
        ]
        if not translations:
            # Ingested and priced, then never paid for. There is nothing to read.
            skipped.append((folder.name, "never translated"))
            continue
        pages = render_reader(
            document,
            segmented,
            translations,
            folder / "reader",
            annotation=read_artifact(Annotation, folder / "annotation.json"),
            glossary=read_artifact(Glossary, folder / "glossary.json"),
            vocalization=read_artifact(Vocalization, folder / "vocalization.json"),
        )
        done += 1
        console.print(
            f"[dim]  {document.title or folder.name} ({len(pages)} file"
            f"{'' if len(pages) == 1 else 's'})[/dim]"
        )

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
        builder = Build(
            source,
            target_language=to,
            source_language=source_language,
            style=style,
            provider_name=provider or settings.provider,
            model=model or settings.model,
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
def cache_clear() -> None:
    """Drop cached translations. Language models are kept."""
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
